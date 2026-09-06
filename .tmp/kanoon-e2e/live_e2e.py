#!/usr/bin/env python3
"""Stateful, redacted live API verifier for the deployed Kanoon data plane."""

from __future__ import annotations

import base64
import csv
import getpass
import hashlib
import io
import json
import os
import random
import re
import secrets
import socket
import ssl
import time
import uuid
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from jsonschema import Draft202012Validator, FormatChecker, RefResolver

BASE_URL = "https://kanoon.esaminu.ir"
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
SPEC_PATH = ROOT / "openapi.json"
SPEC = json.loads(SPEC_PATH.read_text())
STARTED = datetime.now(UTC)
RUN_ID = f"kanoon-e2e-{STARTED:%Y%m%dT%H%M%SZ}-{secrets.token_hex(3)}"
UUID_ZERO = "00000000-0000-4000-8000-000000000001"
TOKEN_KEYS = {"authorization", "access_token", "refresh_token", "draft_token", "password"}
LEAK_PATTERNS = ("traceback", "sqlalchemy", "psycopg", "/app/", "/home/", "secret_key")


def valid_national_code(seed: str) -> str:
    digits = [int(char) for char in hashlib.sha256(seed.encode()).hexdigest() if char.isdigit()][:9]
    if len(set(digits)) == 1:
        digits[0] = (digits[0] + 1) % 10
    remainder = sum(digits[index] * (10 - index) for index in range(9)) % 11
    check = remainder if remainder < 2 else 11 - remainder
    return "".join(map(str, digits)) + str(check)


def operations() -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for path, item in SPEC["paths"].items():
        for method, operation in item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            operation = dict(operation)
            operation["method"] = method.upper()
            operation["path"] = path
            found[operation["operationId"]] = operation
    return found


OPS = operations()


def redact(value: Any, key: str = "") -> Any:
    if key.casefold() in TOKEN_KEYS or any(x in key.casefold() for x in ("signature", "credential")):
        return "<redacted>"
    if isinstance(value, dict):
        return {k: redact(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, key) for v in value]
    if isinstance(value, str):
        value = re.sub(r"(?i)(bearer|draft)\s+[A-Za-z0-9._~+/-]+", r"\1 <redacted>", value)
        if "AWSAccessKeyId=" in value or "X-Amz-Credential=" in value or "X-Amz-Signature=" in value:
            parsed = urlsplit(value)
            value = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "<redacted-presigned-query>", ""))
        if len(value) > 1500:
            return value[:1500] + "…"
    return value


class Runner:
    def __init__(self) -> None:
        self.client = httpx.Client(
            base_url=BASE_URL,
            timeout=httpx.Timeout(25.0),
            follow_redirects=False,
            headers={"User-Agent": f"Kanoon-E2E/{RUN_ID}", "X-Request-ID": RUN_ID},
        )
        self.tests: list[dict[str, Any]] = []
        self.coverage: dict[str, dict[str, Any]] = {
            op_id: {
                "operation_id": op_id,
                "method": op["method"],
                "path": op["path"],
                "positive": "NOT_RUN",
                "negative": "NOT_RUN",
                "integration": "NOT_RUN",
                "result": "BLOCKED",
                "reason": "No executable scenario completed.",
            }
            for op_id, op in OPS.items()
        }
        self.ledger: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.contract_violations: list[dict[str, Any]] = []
        self.findings: list[dict[str, Any]] = []
        self.responses: dict[str, Any] = {}
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self.draft_token: str | None = None
        self.registration_id: str | None = None
        self.profile_media_id: str | None = None
        self.created: dict[str, Any] = {}
        self.admin_headers: dict[str, str] | None = None
        self.remote_openapi_equal: bool | None = None
        self.environment: dict[str, Any] = {}

    def mark_coverage(
        self,
        op_id: str,
        result: str,
        *,
        positive: str | None = None,
        negative: str | None = None,
        integration: str | None = None,
        reason: str = "",
    ) -> None:
        row = self.coverage[op_id]
        if positive:
            row["positive"] = positive
        if negative:
            row["negative"] = negative
        if integration:
            row["integration"] = integration
        rank = {"NOT_APPLICABLE": 0, "BLOCKED": 1, "PASS": 2, "FAIL": 3}
        if rank[result] >= rank[row["result"]]:
            row["result"] = result
        if reason:
            row["reason"] = reason

    def validate_schema(self, op_id: str, status: int, body: Any) -> list[str]:
        response = OPS[op_id].get("responses", {}).get(str(status))
        if response is None:
            return [f"HTTP {status} is undocumented for operation"]
        content = response.get("content", {})
        if not content:
            return []
        schema = None
        for ctype in ("application/json", "text/csv"):
            if ctype in content:
                schema = content[ctype].get("schema")
                break
        if not schema:
            return []
        try:
            Draft202012Validator(
                schema,
                resolver=RefResolver.from_schema(SPEC),
                format_checker=FormatChecker(),
            ).validate(body)
            return []
        except Exception as exc:
            return [f"response schema: {type(exc).__name__}: {str(exc)[:500]}"]

    def request(
        self,
        test_id: str,
        op_id: str,
        scenario: str,
        method: str,
        path: str,
        *,
        kind: str,
        expected: set[int] | range,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        body: Any = None,
        validate_contract: bool = True,
        follow_redirects: bool = False,
        notes: str = "",
    ) -> tuple[httpx.Response | None, Any]:
        started = datetime.now(UTC)
        t0 = time.perf_counter()
        exc_text = None
        response: httpx.Response | None = None
        parsed: Any = None
        try:
            response = self.client.request(
                method,
                path,
                headers=headers,
                params=params,
                json=body,
                follow_redirects=follow_redirects,
            )
            elapsed = round((time.perf_counter() - t0) * 1000, 2)
            ctype = response.headers.get("content-type", "")
            if "json" in ctype:
                try:
                    parsed = response.json()
                except Exception:
                    parsed = response.text
            else:
                parsed = response.text
        except Exception as exc:
            elapsed = round((time.perf_counter() - t0) * 1000, 2)
            exc_text = f"{type(exc).__name__}: {exc}"

        expected_ok = response is not None and response.status_code in expected
        error_quality: list[str] = []
        if response is not None and kind == "negative":
            text = response.text.casefold()
            if response.status_code >= 500:
                error_quality.append("ordinary negative request produced 5xx")
            for marker in LEAK_PATTERNS:
                if marker in text:
                    error_quality.append(f"response contains internal marker: {marker}")
            if response.status_code >= 400:
                if "application/json" not in response.headers.get("content-type", ""):
                    error_quality.append("error response is not JSON")
                elif not isinstance(parsed, dict) or not {"code", "message", "request_id"} <= set(parsed):
                    error_quality.append("error response lacks standard code/message/request_id fields")

        schema_errors: list[str] = []
        if response is not None and validate_contract:
            schema_errors = self.validate_schema(op_id, response.status_code, parsed)
            for err in schema_errors:
                self.contract_violations.append(
                    {"test_id": test_id, "operation_id": op_id, "status": response.status_code, "detail": err}
                )

        result = "PASS" if expected_ok and not error_quality and not (schema_errors and kind == "positive") else "FAIL"
        failure_id = None
        if result == "FAIL":
            failure_id = f"FAIL-{len(self.findings) + 1:03d}"
            severity = "P1" if response is None or (response and response.status_code >= 500 and kind == "positive") else "P3"
            category = "CONTRACT" if schema_errors else ("ERROR_HANDLING" if error_quality else "INTEGRATION")
            finding = {
                "failure_id": failure_id,
                "title": f"{scenario} failed",
                "severity": severity,
                "category": category,
                "operation_id": op_id,
                "endpoint": f"{method} {path}",
                "expected": sorted(expected) if not isinstance(expected, range) else f"{expected.start}-{expected.stop-1}",
                "actual_status": response.status_code if response else None,
                "actual": redact(parsed if response else exc_text),
                "evidence": error_quality + schema_errors,
                "probable_cause": "See observed response and repository analysis; this is refined in the final report.",
                "confidence": "low",
                "recommended_fix": "Correct the endpoint behavior and add a regression test for this scenario.",
                "regression_test": test_id,
            }
            self.findings.append(finding)

        record = {
            "test_id": test_id,
            "timestamp": started.isoformat(),
            "operation_id": op_id,
            "scenario": scenario,
            "kind": kind,
            "result": result,
            "timing_ms": elapsed,
            "status_code": response.status_code if response else None,
            "method": method,
            "path": path,
            "request_headers": redact(headers or {}),
            "request_query": redact(params or {}),
            "request_body": redact(body),
            "response_headers": redact(
                {
                    k: v
                    for k, v in (response.headers.items() if response else [])
                    if k.casefold() in {"content-type", "content-disposition", "location", "retry-after", "x-request-id"}
                }
            ),
            "response_body": redact(parsed),
            "failure_id": failure_id,
            "notes": notes,
        }
        self.tests.append(record)
        if result == "FAIL":
            self.mark_coverage(op_id, "FAIL", reason=scenario)
        elif kind == "positive":
            self.mark_coverage(op_id, "PASS", positive="PASS", reason="Positive scenario passed.")
        else:
            self.coverage[op_id]["negative"] = "PASS"
        return response, parsed

    def blocked(self, op_id: str, scenario: str, reason: str, *, kind: str = "positive") -> None:
        self.tests.append(
            {
                "test_id": f"BLOCK-{len(self.tests)+1:03d}",
                "timestamp": datetime.now(UTC).isoformat(),
                "operation_id": op_id,
                "scenario": scenario,
                "kind": kind,
                "result": "BLOCKED",
                "timing_ms": 0,
                "status_code": None,
                "method": OPS[op_id]["method"],
                "path": OPS[op_id]["path"],
                "failure_id": None,
                "notes": reason,
            }
        )
        self.mark_coverage(op_id, "BLOCKED", positive="BLOCKED" if kind == "positive" else None, reason=reason)

    def preflight(self) -> None:
        addresses = sorted({x[4][0] for x in socket.getaddrinfo("kanoon.esaminu.ir", 443, type=socket.SOCK_STREAM)})
        self.environment["dns_addresses"] = addresses
        context = ssl.create_default_context()
        with socket.create_connection(("kanoon.esaminu.ir", 443), timeout=10) as raw:
            with context.wrap_socket(raw, server_hostname="kanoon.esaminu.ir") as tls:
                cert = tls.getpeercert()
                self.environment["tls_version"] = tls.version()
                self.environment["tls_not_after"] = cert.get("notAfter")
        for n, (path, op_id) in enumerate(
            [("/health/live", "live_health_live_get"), ("/health/ready", "ready_health_ready_get")], 1
        ):
            self.request(f"HEALTH-{n:03d}", op_id, f"GET {path} succeeds with JSON health state", "GET", path, kind="positive", expected={200})
        t0 = time.perf_counter()
        remote = self.client.get("/openapi.json")
        self.environment["openapi_status"] = remote.status_code
        self.environment["openapi_timing_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        if remote.status_code == 200:
            local_canon = json.dumps(SPEC, sort_keys=True, separators=(",", ":"))
            remote_canon = json.dumps(remote.json(), sort_keys=True, separators=(",", ":"))
            self.remote_openapi_equal = local_canon == remote_canon
            self.environment["local_openapi_sha256"] = hashlib.sha256(local_canon.encode()).hexdigest()
            self.environment["remote_openapi_sha256"] = hashlib.sha256(remote_canon.encode()).hexdigest()

    def authentication(self) -> None:
        login = "tenant_login_api_v1_admin_auth_login_post"
        refresh = "tenant_refresh_api_v1_admin_auth_refresh_post"
        self.request("AUTH-001", login, "Malformed login body is rejected", "POST", "/api/v1/admin/auth/login", kind="negative", expected={422}, body={})
        self.request(
            "AUTH-002", login, "Invalid credentials are rejected generically", "POST", "/api/v1/admin/auth/login",
            kind="negative", expected={401}, body={"email": f"{RUN_ID}@example.com", "password": "invalid-password-123"}, validate_contract=False,
        )
        username = os.getenv("ADMIN_USERNAME") or os.getenv("KANOON_E2E_ADMIN_USERNAME")
        password = os.getenv("ADMIN_PASSWORD") or os.getenv("KANOON_E2E_ADMIN_PASSWORD")
        if not (username and password) and os.getenv("KANOON_E2E_PROMPT_CREDENTIALS") == "1":
            username = getpass.getpass("Admin username (hidden): ")
            password = getpass.getpass("Admin password (hidden): ")
        if username and password:
            response, body = self.request(
                "AUTH-003", login, "Administrator login", "POST", "/api/v1/admin/auth/login", kind="positive", expected={200}, body={"email": username, "password": password}
            )
            if response and response.status_code == 200 and isinstance(body, dict):
                self.access_token = body.get("access_token")
                self.refresh_token = body.get("refresh_token")
                self.admin_headers = {"Authorization": f"Bearer {self.access_token}"}
            else:
                self.blocked(refresh, "Valid refresh token", "Administrator login did not yield a token pair.")
        else:
            self.blocked(login, "Administrator login", "ADMIN_USERNAME and ADMIN_PASSWORD were not supplied; prompt values were placeholders.")

        self.request("AUTH-004", refresh, "Malformed refresh token is rejected", "POST", "/api/v1/admin/auth/refresh", kind="negative", expected={422}, body={"refresh_token": "short"})
        self.request("AUTH-005", refresh, "Random well-formed refresh token is rejected", "POST", "/api/v1/admin/auth/refresh", kind="negative", expected={401}, body={"refresh_token": secrets.token_urlsafe(48)}, validate_contract=False)
        if self.refresh_token:
            response, body = self.request("AUTH-006", refresh, "Valid refresh token rotates token pair", "POST", "/api/v1/admin/auth/refresh", kind="positive", expected={200}, body={"refresh_token": self.refresh_token})
            if response and response.status_code == 200:
                old_refresh = self.refresh_token
                self.access_token = body["access_token"]
                self.refresh_token = body["refresh_token"]
                self.admin_headers = {"Authorization": f"Bearer {self.access_token}"}
                self.request("AUTH-007", refresh, "Reusing rotated refresh token is rejected", "POST", "/api/v1/admin/auth/refresh", kind="negative", expected={401}, body={"refresh_token": old_refresh}, validate_contract=False)
                self.request("AUTH-008", "list_banners_api_v1_admin_banners_get", "Refreshed access token reaches protected API", "GET", "/api/v1/admin/banners", kind="positive", expected={200}, headers=self.admin_headers)
        elif self.coverage[refresh]["positive"] == "NOT_RUN":
            self.blocked(refresh, "Valid refresh and rotation", "No valid administrator refresh token was available.")

    def public_reads(self) -> dict[str, Any]:
        definitions = [
            ("site_bootstrap_api_v1_public_site_get", "/api/v1/public/site", None),
            ("banners_api_v1_public_banners_get", "/api/v1/public/banners", None),
            ("news_api_v1_public_news_get", "/api/v1/public/news", "paged"),
            ("announcements_api_v1_public_announcements_get", "/api/v1/public/announcements", "paged"),
            ("honors_api_v1_public_honors_get", "/api/v1/public/honors", "paged"),
            ("staff_api_v1_public_staff_get", "/api/v1/public/staff", None),
            ("pricing_plans_api_v1_public_pricing_plans_get", "/api/v1/public/pricing-plans", None),
            ("exams_api_v1_public_exams_get", "/api/v1/public/exams", None),
            ("school_directory_api_v1_public_school_directory_get", "/api/v1/public/school-directory", "paged"),
            ("sample_exams_api_v1_public_sample_exams_get", "/api/v1/public/sample-exams", "paged"),
            ("gallery_api_v1_public_gallery_get", "/api/v1/public/gallery", "paged"),
            ("blog_snapshot_api_v1_public_blog_snapshot_get", "/api/v1/public/blog/snapshot", None),
            ("list_blog_posts_api_v1_public_blog_get", "/api/v1/public/blog", "paged"),
        ]
        data: dict[str, Any] = {}
        for index, (op_id, path, mode) in enumerate(definitions, 1):
            response, body = self.request(f"PUBLIC-{index:03d}", op_id, "Default public read", "GET", path, kind="positive", expected={200})
            if response and response.status_code == 200:
                data[op_id] = body
                if mode == "paged":
                    self.request(f"PUBLIC-{index:03d}A", op_id, "Pagination page=1 and maximum page_size", "GET", path, kind="positive", expected={200}, params={"page": 1, "page_size": 100})
                    self.request(f"PUBLIC-{index:03d}B", op_id, "Pagination rejects page=0", "GET", path, kind="negative", expected={422}, params={"page": 0})
                    self.request(f"PUBLIC-{index:03d}C", op_id, "Pagination rejects page_size above maximum", "GET", path, kind="negative", expected={422}, params={"page_size": 101})
                    self.request(f"PUBLIC-{index:03d}E", op_id, "Pagination rejects page_size=0", "GET", path, kind="negative", expected={422}, params={"page_size": 0})
                    self.request(f"PUBLIC-{index:03d}D", op_id, "Empty-result page remains valid", "GET", path, kind="positive", expected={200}, params={"page": 999999, "page_size": 1})

        school_op = "school_directory_api_v1_public_school_directory_get"
        self.request("PUBLIC-SEARCH-001", school_op, "Known-nonmatching directory search", "GET", "/api/v1/public/school-directory", kind="positive", expected={200}, params={"search": RUN_ID})

        detail_pairs = [
            ("news_api_v1_public_news_get", "news_detail_api_v1_public_news__slug__get", "/api/v1/public/news/{slug}"),
            ("announcements_api_v1_public_announcements_get", "announcement_detail_api_v1_public_announcements__slug__get", "/api/v1/public/announcements/{slug}"),
            ("gallery_api_v1_public_gallery_get", "gallery_detail_api_v1_public_gallery__slug__get", "/api/v1/public/gallery/{slug}"),
            ("list_blog_posts_api_v1_public_blog_get", "get_blog_post_api_v1_public_blog__slug__get", "/api/v1/public/blog/{slug}"),
        ]
        for index, (list_op, detail_op, template) in enumerate(detail_pairs, 1):
            source = data.get(list_op)
            items = source.get("items", []) if isinstance(source, dict) else []
            if items and isinstance(items[0], dict) and items[0].get("slug"):
                slug = items[0]["slug"]
                response, detail = self.request(f"DETAIL-{index:03d}", detail_op, "List item dereferences by slug", "GET", template.format(slug=slug), kind="positive", expected={200})
                if response and response.status_code == 200:
                    data[detail_op] = detail
                if response and response.status_code == 200 and detail.get("slug") != slug:
                    self.findings.append({"failure_id": f"FAIL-{len(self.findings)+1:03d}", "title": "List/detail slug inconsistency", "severity": "P2", "category": "DATABASE_STATE", "operation_id": detail_op, "endpoint": template, "expected": slug, "actual_status": 200, "actual": detail.get("slug"), "evidence": [], "probable_cause": "List and detail endpoints resolved different records.", "confidence": "high", "recommended_fix": "Use consistent tenant/status/slug filtering.", "regression_test": f"DETAIL-{index:03d}"})
                    self.mark_coverage(detail_op, "FAIL", integration="FAIL", reason="List/detail slug mismatch")
                else:
                    self.coverage[detail_op]["integration"] = "PASS"
            else:
                self.request(f"DETAIL-{index:03d}N", detail_op, "Nonexistent slug is rejected", "GET", template.format(slug=RUN_ID), kind="negative", expected={404}, validate_contract=False)
                self.blocked(detail_op, "Positive detail retrieval", "Public list contained no item that could be safely dereferenced.")
        self.verify_created_public_state(data)
        return data

    def verify_created_public_state(self, data: dict[str, Any]) -> None:
        mappings = [
            ("news", "news_api_v1_public_news_get", "items"),
            ("announcement", "announcements_api_v1_public_announcements_get", "items"),
            ("honor", "honors_api_v1_public_honors_get", "items"),
            ("staff", "staff_api_v1_public_staff_get", None),
            ("pricing", "pricing_plans_api_v1_public_pricing_plans_get", None),
            ("exam", "exams_api_v1_public_exams_get", None),
            ("gallery", "gallery_api_v1_public_gallery_get", "items"),
        ]
        for key, op_id, container in mappings:
            entity_id = self.created.get(key)
            if not entity_id:
                continue
            body = data.get(op_id)
            items = body.get(container, []) if container and isinstance(body, dict) else body
            found = isinstance(items, list) and any(isinstance(item, dict) and item.get("id") == entity_id for item in items)
            self.tests.append(
                {
                    "test_id": f"PUBLIC-CONSISTENCY-{key.upper()}",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "operation_id": op_id,
                    "scenario": f"Admin-created {key} appears in public representation",
                    "kind": "integration",
                    "result": "PASS" if found else "FAIL",
                    "timing_ms": 0,
                    "status_code": 200,
                    "method": "GET",
                    "path": OPS[op_id]["path"],
                    "failure_id": None,
                    "notes": f"entity_id={entity_id}",
                }
            )
            if found:
                self.coverage[op_id]["integration"] = "PASS"
            else:
                failure_id = f"FAIL-{len(self.findings)+1:03d}"
                self.tests[-1]["failure_id"] = failure_id
                self.findings.append(
                    {
                        "failure_id": failure_id,
                        "title": f"Admin-created {key} is absent from public API",
                        "severity": "P2",
                        "category": "CONTENT_PUBLICATION",
                        "operation_id": op_id,
                        "endpoint": f"GET {OPS[op_id]['path']}",
                        "expected": f"Published/active entity {entity_id} is present.",
                        "actual_status": 200,
                        "actual": "Entity was not found in the public response.",
                        "evidence": [f"created entity id {entity_id}"],
                        "probable_cause": "Public visibility filter or persistence mismatch.",
                        "confidence": "high",
                        "recommended_fix": "Align publish/active state and public query predicates.",
                        "regression_test": self.tests[-1]["test_id"],
                    }
                )
                self.mark_coverage(op_id, "FAIL", integration="FAIL", reason=f"Created {key} absent publicly")

    def contact_request(self) -> None:
        op_id = "create_contact_request_api_v1_public_contact_requests_post"
        phone = "+98912" + f"{random.randint(1000000, 9999999)}"
        body = {"name": RUN_ID, "education_level": "E2E", "phone_number": phone}
        response, parsed = self.request("CONTACT-001", op_id, "Create isolated public contact request", "POST", "/api/v1/public/contact-requests", kind="positive", expected={202}, body=body)
        if response and response.status_code == 202:
            self.ledger["contact_requests"].append({"id": parsed.get("id"), "name": RUN_ID})
            self.created["contact_request"] = parsed.get("id")
        self.request("CONTACT-002", op_id, "Contact request below minimum name length is rejected", "POST", "/api/v1/public/contact-requests", kind="negative", expected={422}, body={**body, "name": "x"})
        self.request("CONTACT-003", op_id, "Malformed phone is rejected", "POST", "/api/v1/public/contact-requests", kind="negative", expected={422}, body={**body, "phone_number": "not-a-phone"})
        if self.admin_headers and self.created.get("contact_request"):
            contact_id = self.created["contact_request"]
            response, handled = self.request(
                "CONTACT-ADMIN-001",
                "handle_contact_request_api_v1_admin_contact_requests__entity_id__patch",
                "Admin handles public contact request with internal notes",
                "PATCH",
                f"/api/v1/admin/contact-requests/{contact_id}",
                kind="positive",
                expected={200},
                headers=self.admin_headers,
                body={"status": "CLOSED", "internal_notes": RUN_ID},
            )
            if response and response.status_code == 200:
                coherent = handled.get("status") == "CLOSED" and handled.get("internal_notes") == RUN_ID and handled.get("handled_at") is not None
                self.coverage["handle_contact_request_api_v1_admin_contact_requests__entity_id__patch"]["integration"] = "PASS" if coherent else "FAIL"
                self.ledger["contact_requests"][-1]["cleanup_state"] = "CLOSED"
            self.request(
                "CONTACT-ADMIN-002",
                "list_contact_requests_api_v1_admin_contact_requests_get",
                "Admin list contains submitted contact request",
                "GET",
                "/api/v1/admin/contact-requests",
                kind="positive",
                expected={200},
                headers=self.admin_headers,
                params={"page": 1, "page_size": 100},
            )

    def media_public(self, public_data: dict[str, Any]) -> None:
        op_id = "download_media_api_v1_public_media__media_id__get"
        candidates: list[str] = []

        def scan(v: Any, key: str = "") -> None:
            if isinstance(v, dict):
                for k, item in v.items():
                    scan(item, k)
            elif isinstance(v, list):
                for item in v:
                    scan(item, key)
            elif isinstance(v, str) and key.casefold().endswith(("media_id", "image_id")):
                try:
                    candidates.append(str(uuid.UUID(v)))
                except ValueError:
                    pass

        scan(public_data)
        found = False
        for candidate in dict.fromkeys(candidates):
            response, _ = self.request("MEDIA-PUBLIC-001", op_id, "Public media redirects to object storage", "GET", f"/api/v1/public/media/{candidate}", kind="positive", expected={307}, validate_contract=False)
            if response and response.status_code == 307:
                location = response.headers.get("location")
                if location:
                    t0 = time.perf_counter()
                    obj = httpx.get(location, timeout=25, follow_redirects=True)
                    object_ok = obj.status_code == 200 and bool(obj.content)
                    failure_id = None
                    notes = f"bytes={len(obj.content)}"
                    if not object_ok:
                        failure_id = f"FAIL-{len(self.findings) + 1:03d}"
                        error_code = None
                        error_message = None
                        if "xml" in obj.headers.get("content-type", ""):
                            code_match = re.search(r"<Code>([^<]+)</Code>", obj.text)
                            message_match = re.search(r"<Message>([^<]+)</Message>", obj.text)
                            error_code = code_match.group(1) if code_match else None
                            error_message = message_match.group(1) if message_match else None
                        notes += f" storage_error_code={error_code} message={error_message}"
                        self.findings.append({
                            "failure_id": failure_id,
                            "title": "Public media redirect produces an unusable presigned storage URL",
                            "severity": "P2",
                            "category": "MEDIA_STORAGE",
                            "operation_id": op_id,
                            "endpoint": f"GET /api/v1/public/media/{candidate}",
                            "expected": "307 followed by successful object retrieval (HTTP 200)",
                            "actual_status": obj.status_code,
                            "actual": {"storage_error_code": error_code, "message": error_message, "bytes": len(obj.content)},
                            "evidence": ["API redirect itself was 307", "The presigned URL was followed without modification"],
                            "probable_cause": "The S3-compatible gateway computes a different SigV4/SigV2 canonical request, most likely because the public storage reverse proxy is not preserving the signed Host/path/query or the presign client endpoint does not match the public gateway.",
                            "confidence": "medium",
                            "recommended_fix": "Align KANOON_S3_PUBLIC_ENDPOINT_URL with the browser-visible gateway and configure that proxy to preserve Host, path, and query exactly as signed.",
                            "regression_test": "MEDIA-PUBLIC-002",
                        })
                        self.mark_coverage(op_id, "FAIL", integration="FAIL", reason="Presigned object URL returned storage signature mismatch")
                    self.tests.append({"test_id": "MEDIA-PUBLIC-002", "timestamp": datetime.now(UTC).isoformat(), "operation_id": op_id, "scenario": "Follow public media redirect and fetch object bytes", "kind": "integration", "result": "PASS" if object_ok else "FAIL", "timing_ms": round((time.perf_counter()-t0)*1000,2), "status_code": obj.status_code, "method": "GET", "path": "<redacted-presigned-object-url>", "failure_id": failure_id, "notes": notes})
                    if object_ok:
                        self.coverage[op_id]["integration"] = "PASS"
                found = True
                break
        self.request("MEDIA-PUBLIC-NEG-001", op_id, "Nonexistent public media is rejected", "GET", f"/api/v1/public/media/{uuid.uuid4()}", kind="negative", expected={404}, validate_contract=False)
        self.request("MEDIA-PUBLIC-NEG-002", op_id, "Malformed media UUID is rejected", "GET", "/api/v1/public/media/not-a-uuid", kind="negative", expected={422})
        if not found:
            self.blocked(op_id, "Positive public media download", "No publicly referenced READY media was discoverable.")

    def registration(self, public_data: dict[str, Any]) -> None:
        create_op = "create_registration_api_v1_public_registrations_post"
        exams = public_data.get("exams_api_v1_public_exams_get")
        if not isinstance(exams, list) or not exams:
            self.request("REG-NEG-001", create_op, "Registration rejects nonexistent exam", "POST", "/api/v1/public/registrations", kind="negative", expected={404}, body={"exam_offering_id": str(uuid.uuid4()), "phone_number": "+989121234567"}, validate_contract=False)
            self.request("REG-NEG-002", create_op, "Registration rejects malformed body", "POST", "/api/v1/public/registrations", kind="negative", expected={422}, body={})
            self.blocked(create_op, "Create registration draft", "No public exam offering was available; administrator access was unavailable to create one.")
            self.block_registration_dependents("No registration draft could be created because no public exam offering exists.")
            return

        phone = "+98913" + f"{random.randint(1000000,9999999)}"
        exam_id = self.created.get("exam") or exams[0]["id"]
        create_body = {"exam_offering_id": exam_id, "phone_number": phone}
        if self.created.get("pricing"):
            create_body["selected_pricing_plan_id"] = self.created["pricing"]
        response, parsed = self.request("REG-001", create_op, "Create registration draft from discovered linked exam/pricing", "POST", "/api/v1/public/registrations", kind="positive", expected={201}, body=create_body)
        if not response or response.status_code != 201:
            self.block_registration_dependents("Discovered exam did not permit creation of a registration draft.")
            return
        self.registration_id = parsed["registration"]["id"]
        self.draft_token = parsed["draft_token"]
        self.ledger["registrations"].append({"id": self.registration_id, "phone": phone})
        auth = {"Authorization": f"Draft {self.draft_token}"}

        get_op = "get_registration_api_v1_public_registrations__registration_id__get"
        path = f"/api/v1/public/registrations/{self.registration_id}"
        self.request("REG-002", get_op, "Read newly created draft", "GET", path, kind="positive", expected={200}, headers=auth)
        self.request("REG-003", get_op, "Missing draft authorization is rejected", "GET", path, kind="negative", expected={401}, validate_contract=False)
        self.request("REG-004", get_op, "Random draft token is rejected without existence leak", "GET", path, kind="negative", expected={404}, headers={"Authorization": f"Draft {secrets.token_urlsafe(48)}"}, validate_contract=False)
        self.request("REG-005", get_op, "Malformed registration UUID is rejected", "GET", "/api/v1/public/registrations/not-a-uuid", kind="negative", expected={422}, headers=auth)

        patch_op = "patch_registration_api_v1_public_registrations__registration_id__patch"
        patch = {"first_name": "E2E", "last_name": RUN_ID[-20:], "gender": "OTHER", "national_code": valid_national_code(RUN_ID), "father_name": "E2E Father", "birth_date": "2005-01-02", "home_phone": "02112345678", "postal_code": "1234567890", "address": "E2E test address", "extra_answers": {"run_id": RUN_ID}}
        response, body = self.request("REG-006", patch_op, "Patch representative optional registration fields", "PATCH", path, kind="positive", expected={200}, headers=auth, body=patch)
        if response and response.status_code == 200 and body.get("first_name") != "E2E":
            self.mark_coverage(patch_op, "FAIL", integration="FAIL", reason="Patch response did not persist value")
        self.request("REG-007", patch_op, "Patch rejects invalid enum", "PATCH", path, kind="negative", expected={422}, headers=auth, body={"gender": "INVALID"})
        self.request("REG-008", patch_op, "Patch rejects additional property", "PATCH", path, kind="negative", expected={422}, headers=auth, body={"unexpected": True})

        contacts_op = "put_contacts_api_v1_public_registrations__registration_id__contacts_put"
        contacts = {"contacts": [{"position": 1, "name": "Parent One", "phone_number": "+989121234568", "relationship": "Parent"}, {"position": 2, "name": "Parent Two", "phone_number": "+989121234569", "relationship": "Parent"}]}
        self.request("REG-009", contacts_op, "Replace registration contacts", "PUT", path + "/contacts", kind="positive", expected={200}, headers=auth, body=contacts)
        self.request("REG-010", contacts_op, "Duplicate contact positions are rejected", "PUT", path + "/contacts", kind="negative", expected={422}, headers=auth, body={"contacts": [contacts["contacts"][0], contacts["contacts"][0]]})
        self.request("REG-011", get_op, "Registration read reflects persisted patch and contacts", "GET", path, kind="positive", expected={200}, headers=auth)

        submit_op = "submit_registration_api_v1_public_registrations__registration_id__submit_post"
        self.request("REG-012", submit_op, "Premature submission is rejected", "POST", path + "/submit", kind="negative", expected={400}, headers=auth, validate_contract=False)

        self.profile_upload(path, auth)

        otp_send = "send_otp_api_v1_public_registrations__registration_id__otp_send_post"
        otp_verify = "verify_otp_api_v1_public_registrations__registration_id__otp_verify_post"
        self.request("OTP-001", otp_send, "Invalid draft token prevents OTP delivery", "POST", path + "/otp/send", kind="negative", expected={404}, headers={"Authorization": f"Draft {secrets.token_urlsafe(48)}"}, validate_contract=False)
        self.request("OTP-002", otp_verify, "Malformed OTP is rejected by schema", "POST", path + "/otp/verify", kind="negative", expected={422}, headers=auth, body={"code": "12ab"})
        self.request("OTP-003", otp_verify, "Verification without a sent challenge is rejected", "POST", path + "/otp/verify", kind="negative", expected={400}, headers=auth, body={"code": "000000"}, validate_contract=False)
        self.blocked(otp_send, "Successful OTP delivery", "No explicitly authorized test phone or deployed OTP-test mechanism was supplied; no SMS was sent.")
        self.blocked(otp_verify, "Successful OTP verification", "No authorized OTP retrieval/test-number mechanism is exposed by the deployed API.")

        rotate_op = "rotate_draft_token_api_v1_public_registrations__registration_id__token_rotate_post"
        old = self.draft_token
        response, rotated = self.request("REG-013", rotate_op, "Rotate draft token", "POST", path + "/token/rotate", kind="positive", expected={200}, headers=auth)
        if response and response.status_code == 200:
            self.draft_token = rotated["draft_token"]
            auth = {"Authorization": f"Draft {self.draft_token}"}
            self.request("REG-014", get_op, "New draft token works", "GET", path, kind="positive", expected={200}, headers=auth)
            self.request("REG-015", get_op, "Old rotated draft token is revoked", "GET", path, kind="negative", expected={404}, headers={"Authorization": f"Draft {old}"}, validate_contract=False)
            self.coverage[rotate_op]["integration"] = "PASS"

        pay_op = "initiate_payment_api_v1_public_registrations__registration_id__payment_post"
        pay_status = "payment_status_api_v1_public_registrations__registration_id__payment_status_get"
        self.request("PAY-001", pay_op, "Payment before eligible registration is rejected", "POST", path + "/payment", kind="negative", expected={400, 409}, headers={**auth, "Idempotency-Key": f"{RUN_ID}-payment"}, validate_contract=False)
        self.request("PAY-002", pay_op, "Missing idempotency key is rejected", "POST", path + "/payment", kind="negative", expected={422}, headers=auth)
        self.request("PAY-003", pay_op, "Too-short idempotency key is rejected", "POST", path + "/payment", kind="negative", expected={422}, headers={**auth, "Idempotency-Key": "short"})
        self.request("PAY-004", pay_status, "Read initial payment status", "GET", path + "/payment/status", kind="positive", expected={200}, headers=auth)
        self.blocked(pay_op, "Eligible payment initiation and idempotency replay", "Registration cannot become eligible without successful OTP verification; no OTP retrieval mechanism is authorized.")
        self.blocked(submit_op, "Successful registration submission", "Successful OTP verification is blocked.")
        self.admin_registration_workflow(auth)

    def admin_registration_workflow(self, draft_headers: dict[str, str]) -> None:
        if not self.admin_headers or not self.registration_id:
            return
        rid = self.registration_id
        list_op = "list_registrations_api_v1_admin_registrations_get"
        detail_op = "registration_detail_api_v1_admin_registrations__registration_id__get"
        update_op = "update_registration_api_v1_admin_registrations__registration_id__patch"
        response, found = self.request(
            "ADMIN-REG-001", list_op, "Search admin registrations for unique test student", "GET",
            "/api/v1/admin/registrations", kind="positive", expected={200}, headers=self.admin_headers,
            params={"search": "E2E", "page": 1, "page_size": 100},
        )
        if response and response.status_code == 200:
            present = any(item.get("id") == rid for item in found.get("items", []))
            self.coverage[list_op]["integration"] = "PASS" if present else "FAIL"
        self.request(
            "ADMIN-REG-002", list_op, "Admin registration status filter", "GET", "/api/v1/admin/registrations",
            kind="positive", expected={200}, headers=self.admin_headers, params={"status": "PHONE_VERIFICATION_REQUIRED"},
        )
        response, detail = self.request(
            "ADMIN-REG-003", detail_op, "Admin detail matches public registration", "GET",
            f"/api/v1/admin/registrations/{rid}", kind="positive", expected={200}, headers=self.admin_headers,
        )
        if response and response.status_code == 200:
            self.coverage[detail_op]["integration"] = "PASS" if detail.get("id") == rid and detail.get("first_name") == "E2E" else "FAIL"
        self.request(
            "ADMIN-REG-004", update_op, "Persist admin internal notes", "PATCH",
            f"/api/v1/admin/registrations/{rid}", kind="positive", expected={200}, headers=self.admin_headers,
            body={"internal_notes": RUN_ID},
        )
        self.request(
            "ADMIN-REG-005", update_op, "Reject illegal draft-to-submitted admin transition", "PATCH",
            f"/api/v1/admin/registrations/{rid}", kind="negative", expected={400}, headers=self.admin_headers,
            body={"status": "SUBMITTED"}, validate_contract=False,
        )
        export_op = "export_registrations_api_v1_admin_registrations_export_csv_get"
        response, _ = self.request(
            "ADMIN-CSV-001", export_op, "Export registrations as real CSV", "GET",
            "/api/v1/admin/registrations/export.csv", kind="positive", expected={200}, headers=self.admin_headers,
            validate_contract=False,
        )
        if response and response.status_code == 200:
            try:
                rows = list(csv.reader(io.StringIO(response.text.lstrip("\ufeff"))))
                header_ok = rows and rows[0][:3] == ["id", "exam_offering_id", "phone_number"]
                present = any(row and row[0] == rid for row in rows[1:])
                artifact_ok = "text/csv" in response.headers.get("content-type", "") and header_ok and present
            except csv.Error:
                artifact_ok = False
            self.coverage[export_op]["integration"] = "PASS" if artifact_ok else "FAIL"
            if not artifact_ok:
                self.mark_coverage(export_op, "FAIL", integration="FAIL", reason="CSV artifact/header/test row validation failed")
        # Cancel at the end as the API-supported terminal cleanup state, then prove draft immutability.
        response, _ = self.request(
            "ADMIN-REG-006", update_op, "Cancel test registration", "PATCH",
            f"/api/v1/admin/registrations/{rid}", kind="positive", expected={200}, headers=self.admin_headers,
            body={"status": "CANCELLED", "internal_notes": f"{RUN_ID} cleanup"},
        )
        if response and response.status_code == 200:
            self.ledger["registrations"][0]["cleanup_state"] = "CANCELLED"
            self.request(
                "ADMIN-REG-007", "patch_registration_api_v1_public_registrations__registration_id__patch",
                "Cancelled registration is immutable through draft API", "PATCH",
                f"/api/v1/public/registrations/{rid}", kind="negative", expected={400}, headers=draft_headers,
                body={"first_name": "Should Not Persist"}, validate_contract=False,
            )

    def profile_upload(self, registration_path: str, auth: dict[str, str]) -> None:
        init_op = "initiate_profile_image_upload_api_v1_public_registrations__registration_id__profile_image_upload_post"
        complete_op = "complete_profile_image_upload_api_v1_public_registrations__registration_id__profile_image__media_id__complete_post"
        png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
        digest = hashlib.sha256(png).hexdigest()
        request_body = {"filename": f"{RUN_ID}.png", "mime_type": "image/png", "size_bytes": len(png), "visibility": "PRIVATE"}
        response, body = self.request("MEDIA-PROFILE-001", init_op, "Initiate private profile image upload", "POST", registration_path + "/profile-image/upload", kind="positive", expected={201}, headers=auth, body=request_body)
        if not response or response.status_code != 201:
            self.blocked(complete_op, "Complete profile image upload", "Upload initiation failed.")
            return
        media_id = body["media_id"]
        self.profile_media_id = media_id
        self.ledger["media"].append({"id": media_id, "visibility": "PRIVATE", "filename": request_body["filename"]})
        self.request("MEDIA-PROFILE-002", complete_op, "Completion before object upload is rejected without 5xx", "POST", registration_path + f"/profile-image/{media_id}/complete", kind="negative", expected={404, 422}, headers=auth, body={"sha256": digest, "width": 1, "height": 1}, validate_contract=False)
        try:
            upload = httpx.post(body["upload_url"], data=body["form_fields"], files={"file": (request_body["filename"], png, "image/png")}, timeout=30)
            self.tests.append({"test_id": "MEDIA-PROFILE-003", "timestamp": datetime.now(UTC).isoformat(), "operation_id": init_op, "scenario": "Upload bytes to presigned object-storage endpoint", "kind": "integration", "result": "PASS" if upload.status_code in {200, 201, 204} else "FAIL", "timing_ms": round(upload.elapsed.total_seconds()*1000,2), "status_code": upload.status_code, "method": "POST", "path": "<redacted-presigned-upload-url>", "failure_id": None, "notes": f"bytes={len(png)}"})
        except Exception as exc:
            self.tests.append({"test_id": "MEDIA-PROFILE-003", "timestamp": datetime.now(UTC).isoformat(), "operation_id": init_op, "scenario": "Upload bytes to presigned object-storage endpoint", "kind": "integration", "result": "FAIL", "timing_ms": 0, "status_code": None, "method": "POST", "path": "<redacted-presigned-upload-url>", "failure_id": None, "notes": f"{type(exc).__name__}: {exc}"})
            self.mark_coverage(init_op, "FAIL", integration="FAIL", reason="Object storage upload failed")
            self.blocked(complete_op, "Complete profile image upload", "Object storage upload failed.")
            return
        if upload.status_code not in {200, 201, 204}:
            self.mark_coverage(init_op, "FAIL", integration="FAIL", reason=f"Object storage upload returned {upload.status_code}")
            self.blocked(complete_op, "Complete profile image upload", "Object storage upload was rejected.")
            return
        response, meta = self.request("MEDIA-PROFILE-004", complete_op, "Complete profile image after real object upload", "POST", registration_path + f"/profile-image/{media_id}/complete", kind="positive", expected={200}, headers=auth, body={"sha256": digest, "width": 1, "height": 1})
        if response and response.status_code == 200:
            expected = {"id": media_id, "size_bytes": len(png), "mime_type": "image/png", "width": 1, "height": 1, "visibility": "PRIVATE", "status": "READY"}
            mismatches = {k: (expected[k], meta.get(k)) for k in expected if meta.get(k) != expected[k]}
            if mismatches:
                self.mark_coverage(complete_op, "FAIL", integration="FAIL", reason=f"Metadata mismatch: {mismatches}")
            else:
                self.coverage[complete_op]["integration"] = "PASS"
            public_op = "download_media_api_v1_public_media__media_id__get"
            self.request("MEDIA-PRIVATE-001", public_op, "PRIVATE profile media is not publicly downloadable", "GET", f"/api/v1/public/media/{media_id}", kind="negative", expected={404}, validate_contract=False)

    def block_registration_dependents(self, reason: str) -> None:
        for op_id in [
            "get_registration_api_v1_public_registrations__registration_id__get",
            "patch_registration_api_v1_public_registrations__registration_id__patch",
            "rotate_draft_token_api_v1_public_registrations__registration_id__token_rotate_post",
            "initiate_profile_image_upload_api_v1_public_registrations__registration_id__profile_image_upload_post",
            "complete_profile_image_upload_api_v1_public_registrations__registration_id__profile_image__media_id__complete_post",
            "put_contacts_api_v1_public_registrations__registration_id__contacts_put",
            "send_otp_api_v1_public_registrations__registration_id__otp_send_post",
            "verify_otp_api_v1_public_registrations__registration_id__otp_verify_post",
            "submit_registration_api_v1_public_registrations__registration_id__submit_post",
            "initiate_payment_api_v1_public_registrations__registration_id__payment_post",
            "payment_status_api_v1_public_registrations__registration_id__payment_status_get",
        ]:
            self.blocked(op_id, "Stateful registration dependency", reason)

    def callback_negatives(self) -> None:
        op = "payment_callback_api_v1_public_payments_callback__provider_name__get"
        self.request("CALLBACK-PAY-001", op, "Payment callback missing state is rejected", "GET", "/api/v1/public/payments/callback/nonexistent", kind="negative", expected={422})
        self.request("CALLBACK-PAY-002", op, "Unknown payment provider with tampered state is rejected", "GET", "/api/v1/public/payments/callback/nonexistent", kind="negative", expected={404}, params={"state": "tampered"}, validate_contract=False)
        self.request("CALLBACK-PAY-003", op, "Configured mock provider rejects tampered callback state", "GET", "/api/v1/public/payments/callback/mock", kind="negative", expected={401}, params={"state": "tampered"}, validate_contract=False)
        self.blocked(op, "Legitimate payment callback", "No eligible sandbox payment and signed callback state were available; no financial transaction was attempted.")

        internal = "record_build_result_api_v1_internal_site_builds__request_id__result_post"
        body = {"tenant_id": str(uuid.uuid4()), "status": "FAILED", "error": RUN_ID, "retryable": False}
        path = f"/api/v1/internal/site-builds/{uuid.uuid4()}/result"
        self.request("CALLBACK-BUILD-001", internal, "Unsigned internal build callback is rejected", "POST", path, kind="negative", expected={401}, body=body, validate_contract=False)
        self.request("CALLBACK-BUILD-002", internal, "Invalid internal callback signature is rejected", "POST", path, kind="negative", expected={401}, headers={"X-Kanoon-Timestamp": str(int(time.time())), "X-Kanoon-Signature": "00" * 32}, body=body, validate_contract=False)
        self.request("CALLBACK-BUILD-003", internal, "Stale/tampered internal callback is rejected", "POST", path, kind="negative", expected={401}, headers={"X-Kanoon-Timestamp": "1", "X-Kanoon-Signature": "ff" * 32}, body=body, validate_contract=False)
        self.blocked(internal, "Valid signed build callback", "No authorized deployed callback signing secret or generated callback payload was available.")

    def admin_surface(self) -> None:
        admin_ops = {op_id: op for op_id, op in OPS.items() if op["path"].startswith("/api/v1/admin/") and "/auth/" not in op["path"]}
        auth_headers = {"Authorization": f"Bearer {self.access_token}"} if self.access_token else None
        for index, (op_id, op) in enumerate(admin_ops.items(), 1):
            path = op["path"]
            path = path.replace("{post_id}", str(uuid.uuid4())).replace("{media_id}", str(uuid.uuid4())).replace("{album_id}", str(uuid.uuid4())).replace("{entity_id}", str(uuid.uuid4())).replace("{registration_id}", self.registration_id or str(uuid.uuid4())).replace("{resource}", "banners")
            params: dict[str, Any] = {}
            if op_id == "list_posts_api_v1_admin_posts_get":
                params["kind"] = "NEWS"
            self.request(f"ADMIN-AUTH-{index:03d}", op_id, "Protected admin operation rejects anonymous request", op["method"], path, kind="negative", expected={401}, params=params, body={} if op["method"] in {"POST", "PUT", "PATCH"} else None, validate_contract=False)
            if auth_headers is None:
                self.blocked(op_id, "Authenticated administrator scenario", "Administrator credentials were not supplied.")

        representative = "list_banners_api_v1_admin_banners_get"
        self.request("ADMIN-AUTH-RANDOM", representative, "Random bearer token is rejected", "GET", "/api/v1/admin/banners", kind="negative", expected={401}, headers={"Authorization": f"Bearer {secrets.token_urlsafe(48)}"}, validate_contract=False)
        self.request("ADMIN-AUTH-MALFORMED", representative, "Malformed authorization scheme is rejected", "GET", "/api/v1/admin/banners", kind="negative", expected={401}, headers={"Authorization": "Basic invalid"}, validate_contract=False)

        if auth_headers:
            self.admin_authenticated(auth_headers)

    def admin_authenticated(self, headers: dict[str, str]) -> None:
        self.admin_upload_asset(headers, "image", "PUBLIC")
        self.admin_upload_asset(headers, "document", "PUBLIC")
        self.admin_upload_asset(headers, "private", "PRIVATE")
        self.admin_content_mutations(headers)
        self.admin_blog_workflow(headers)
        self.admin_reads(headers)

        # A lossless restore is impossible when the initial public profile is null: the PUT schema
        # requires a profile and no delete/reset operation exists. Do not mutate it.
        profile_op = "replace_school_profile_api_v1_admin_school_profile_put"
        self.blocked(
            profile_op,
            "Reversible school-profile replacement",
            "Initial profile is null and the API has no lossless restore-to-null operation.",
        )

    def admin_upload_asset(
        self, headers: dict[str, str], asset_key: str, visibility: str
    ) -> str | None:
        init_op = "initiate_upload_api_v1_admin_media_uploads_post"
        complete_op = "complete_upload_api_v1_admin_media_uploads__media_id__complete_post"
        if asset_key == "document":
            payload = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n"
            filename = f"{RUN_ID}.pdf"
            mime = "application/pdf"
            dimensions = {}
        else:
            payload = base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
            )
            filename = f"{RUN_ID}-{asset_key}.png"
            mime = "image/png"
            dimensions = {"width": 1, "height": 1}
        body = {
            "filename": filename,
            "mime_type": mime,
            "size_bytes": len(payload),
            "alt_text": f"{RUN_ID} {asset_key}",
            "visibility": visibility,
        }
        response, upload_data = self.request(
            f"ADMIN-MEDIA-{asset_key}-001",
            init_op,
            f"Initiate {visibility.lower()} admin {asset_key} upload",
            "POST",
            "/api/v1/admin/media/uploads",
            kind="positive",
            expected={201},
            headers=headers,
            body=body,
        )
        if not response or response.status_code != 201:
            self.blocked(complete_op, f"Complete admin {asset_key} upload", "Upload initiation failed.")
            return None
        media_id = upload_data["media_id"]
        self.ledger["media"].append(
            {"id": media_id, "filename": filename, "visibility": visibility, "status": "PENDING"}
        )

        # Exactly one completion-before-upload negative is sufficient and bounded.
        if asset_key == "image":
            self.request(
                "ADMIN-MEDIA-PREMATURE",
                complete_op,
                "Completion before object upload is rejected without 5xx",
                "POST",
                f"/api/v1/admin/media/uploads/{media_id}/complete",
                kind="negative",
                expected={404, 422},
                headers=headers,
                body={"sha256": hashlib.sha256(payload).hexdigest(), **dimensions},
                validate_contract=False,
            )
        t0 = time.perf_counter()
        try:
            stored = httpx.post(
                upload_data["upload_url"],
                data=upload_data["form_fields"],
                files={"file": (filename, payload, mime)},
                timeout=30,
            )
            storage_ok = stored.status_code in {200, 201, 204}
            storage_status = stored.status_code
            storage_note = f"bytes={len(payload)}"
            if not storage_ok and "xml" in stored.headers.get("content-type", ""):
                code = re.search(r"<Code>([^<]+)</Code>", stored.text)
                storage_note += f" storage_error={code.group(1) if code else 'unknown'}"
        except Exception as exc:
            storage_ok = False
            storage_status = None
            storage_note = f"{type(exc).__name__}: {exc}"
        failure_id = None
        if not storage_ok:
            failure_id = f"FAIL-{len(self.findings) + 1:03d}"
            self.findings.append(
                {
                    "failure_id": failure_id,
                    "title": f"Presigned {asset_key} upload is unusable",
                    "severity": "P1",
                    "category": "MEDIA_STORAGE",
                    "operation_id": init_op,
                    "endpoint": "POST /api/v1/admin/media/uploads → presigned storage endpoint",
                    "expected": "Storage accepts the exact declared bytes and content type.",
                    "actual_status": storage_status,
                    "actual": storage_note,
                    "evidence": ["Presigned fields and bytes were submitted without modification"],
                    "probable_cause": "Public S3 proxy/presign endpoint canonicalization is inconsistent.",
                    "confidence": "medium",
                    "recommended_fix": "Preserve signed Host/path/query/body at the storage proxy and align the public presign endpoint.",
                    "regression_test": f"ADMIN-MEDIA-{asset_key}-002",
                }
            )
            self.mark_coverage(init_op, "FAIL", integration="FAIL", reason=storage_note)
        self.tests.append(
            {
                "test_id": f"ADMIN-MEDIA-{asset_key}-002",
                "timestamp": datetime.now(UTC).isoformat(),
                "operation_id": init_op,
                "scenario": "Upload bytes to presigned storage endpoint",
                "kind": "integration",
                "result": "PASS" if storage_ok else "FAIL",
                "timing_ms": round((time.perf_counter() - t0) * 1000, 2),
                "status_code": storage_status,
                "method": "POST",
                "path": "<redacted-presigned-upload-url>",
                "failure_id": failure_id,
                "notes": storage_note,
            }
        )
        if not storage_ok:
            self.blocked(complete_op, f"Complete admin {asset_key} upload", "Object upload failed.")
            return None
        response, metadata = self.request(
            f"ADMIN-MEDIA-{asset_key}-003",
            complete_op,
            f"Complete real admin {asset_key} upload",
            "POST",
            f"/api/v1/admin/media/uploads/{media_id}/complete",
            kind="positive",
            expected={200},
            headers=headers,
            body={"sha256": hashlib.sha256(payload).hexdigest(), **dimensions},
        )
        if not response or response.status_code != 200:
            return None
        expected_meta = {
            "id": media_id,
            "mime_type": mime,
            "size_bytes": len(payload),
            "visibility": visibility,
            "status": "READY",
        }
        mismatch = {key: (value, metadata.get(key)) for key, value in expected_meta.items() if metadata.get(key) != value}
        if mismatch:
            self.mark_coverage(complete_op, "FAIL", integration="FAIL", reason=f"Metadata mismatch: {mismatch}")
            return None
        self.created[f"media_{asset_key}"] = media_id
        self.ledger["media"][-1]["status"] = "READY"
        if visibility == "PRIVATE":
            self.request(
                f"ADMIN-MEDIA-{asset_key}-004",
                "download_media_api_v1_public_media__media_id__get",
                "PRIVATE admin media is not publicly downloadable",
                "GET",
                f"/api/v1/public/media/{media_id}",
                kind="negative",
                expected={404},
                validate_contract=False,
            )
        return media_id

    def admin_content_mutations(self, headers: dict[str, str]) -> None:
        now = datetime.now(UTC)
        suffix = RUN_ID.split("-")[-1]
        slug_prefix = RUN_ID.lower()
        published_at = now.isoformat()
        news = {
            "kind": "NEWS",
            "title": f"{RUN_ID} news",
            "slug": f"{slug_prefix}-news",
            "summary": "isolated E2E news",
            "body": "initial E2E body",
            "status": "DRAFT",
            "published_at": None,
        }
        response, item = self.request(
            "ADMIN-CONTENT-001", "create_post_api_v1_admin_posts_post", "Create draft news", "POST",
            "/api/v1/admin/posts", kind="positive", expected={201}, headers=headers, body=news,
        )
        if response and response.status_code == 201:
            self.created["news"] = item["id"]
            self.created["news_slug"] = news["slug"]
            self.ledger["posts"].append({"id": item["id"], "slug": news["slug"], "kind": "NEWS"})
            news.update({"title": f"{RUN_ID} news updated", "body": "updated E2E body", "status": "PUBLISHED", "published_at": published_at})
            self.request(
                "ADMIN-CONTENT-002", "update_post_api_v1_admin_posts__entity_id__put", "Publish/update news", "PUT",
                f"/api/v1/admin/posts/{item['id']}", kind="positive", expected={200}, headers=headers, body=news,
            )
        announcement = {
            "kind": "ANNOUNCEMENT",
            "title": f"{RUN_ID} announcement",
            "slug": f"{slug_prefix}-announcement",
            "summary": "isolated E2E announcement",
            "body": "announcement body",
            "status": "PUBLISHED",
            "published_at": published_at,
        }
        response, item = self.request(
            "ADMIN-CONTENT-003", "create_post_api_v1_admin_posts_post", "Create published announcement", "POST",
            "/api/v1/admin/posts", kind="positive", expected={201}, headers=headers, body=announcement,
        )
        if response and response.status_code == 201:
            self.created["announcement"] = item["id"]
            self.created["announcement_slug"] = announcement["slug"]
            self.ledger["posts"].append({"id": item["id"], "slug": announcement["slug"], "kind": "ANNOUNCEMENT"})
        self.request(
            "ADMIN-CONTENT-NEG-001", "create_post_api_v1_admin_posts_post", "Generic posts endpoint rejects BLOG kind", "POST",
            "/api/v1/admin/posts", kind="negative", expected={422}, headers=headers,
            body={**news, "kind": "BLOG", "slug": f"{slug_prefix}-wrong-blog"},
        )

        image_id = self.created.get("media_image")
        if image_id:
            banner = {
                "title": f"{RUN_ID} banner",
                "description": "E2E banner",
                "image_id": image_id,
                "target_url": "https://kanoon.esaminu.ir/",
                "sort_order": -99999,
                "status": "PUBLISHED",
                "starts_at": None,
                "ends_at": None,
            }
            response, item = self.request(
                "ADMIN-CONTENT-004", "create_banner_api_v1_admin_banners_post", "Create published banner with real media", "POST",
                "/api/v1/admin/banners", kind="positive", expected={201}, headers=headers, body=banner,
            )
            if response and response.status_code == 201:
                self.created["banner"] = item["id"]
                self.ledger["banners"].append({"id": item["id"]})
                banner["title"] += " updated"
                self.request(
                    "ADMIN-CONTENT-005", "update_banner_api_v1_admin_banners__entity_id__put", "Update banner", "PUT",
                    f"/api/v1/admin/banners/{item['id']}", kind="positive", expected={200}, headers=headers, body=banner,
                )
        else:
            for op in ["create_banner_api_v1_admin_banners_post", "update_banner_api_v1_admin_banners__entity_id__put"]:
                self.blocked(op, "Banner lifecycle with uploaded media", "Real public media upload did not complete.")

        category = {"name": f"{RUN_ID} category", "slug": f"{slug_prefix}-category", "description": "E2E", "sort_order": -99999, "is_active": True}
        response, item = self.request(
            "ADMIN-CONTENT-006", "create_honor_category_api_v1_admin_honor_categories_post", "Create honor category", "POST",
            "/api/v1/admin/honor-categories", kind="positive", expected={201}, headers=headers, body=category,
        )
        if response and response.status_code == 201:
            self.created["honor_category"] = item["id"]
            self.ledger["honor-categories"].append({"id": item["id"], "slug": category["slug"]})
            category["description"] = "E2E updated"
            self.request(
                "ADMIN-CONTENT-007", "update_honor_category_api_v1_admin_honor_categories__entity_id__put", "Update honor category", "PUT",
                f"/api/v1/admin/honor-categories/{item['id']}", kind="positive", expected={200}, headers=headers, body=category,
            )
            honor = {"category_id": item["id"], "student_name": f"E2E {suffix}", "title": f"{RUN_ID} honor", "description": "E2E", "year": 1405, "rank": 1, "sort_order": -99999, "status": "PUBLISHED"}
            hresp, hitem = self.request(
                "ADMIN-CONTENT-008", "create_honor_api_v1_admin_honors_post", "Create published honor", "POST",
                "/api/v1/admin/honors", kind="positive", expected={201}, headers=headers, body=honor,
            )
            if hresp and hresp.status_code == 201:
                self.created["honor"] = hitem["id"]
                self.ledger["honors"].append({"id": hitem["id"]})
                honor["title"] += " updated"
                self.request(
                    "ADMIN-CONTENT-009", "update_honor_api_v1_admin_honors__entity_id__put", "Update honor", "PUT",
                    f"/api/v1/admin/honors/{hitem['id']}", kind="positive", expected={200}, headers=headers, body=honor,
                )

        staff = {"first_name": "E2E", "last_name": suffix, "display_name": f"{RUN_ID} staff", "member_type": "OTHER", "title": "E2E Engineer", "biography": "E2E", "sort_order": -99999, "is_active": True}
        response, item = self.request(
            "ADMIN-CONTENT-010", "create_staff_api_v1_admin_staff_post", "Create active staff", "POST",
            "/api/v1/admin/staff", kind="positive", expected={201}, headers=headers, body=staff,
        )
        if response and response.status_code == 201:
            self.created["staff"] = item["id"]
            self.ledger["staff"].append({"id": item["id"]})
            staff["title"] = "E2E Engineer Updated"
            self.request(
                "ADMIN-CONTENT-011", "update_staff_api_v1_admin_staff__entity_id__put", "Update staff", "PUT",
                f"/api/v1/admin/staff/{item['id']}", kind="positive", expected={200}, headers=headers, body=staff,
            )

        pricing = {"title": f"{RUN_ID} pricing", "slug": f"{slug_prefix}-pricing", "description": "E2E plan", "mode": "ONLINE", "amount": 1000, "currency": "IRR", "features": ["e2e"], "sort_order": -99999, "is_featured": True, "status": "PUBLISHED"}
        response, item = self.request(
            "ADMIN-CONTENT-012", "create_pricing_api_v1_admin_pricing_plans_post", "Create published pricing plan", "POST",
            "/api/v1/admin/pricing-plans", kind="positive", expected={201}, headers=headers, body=pricing,
        )
        if response and response.status_code == 201:
            self.created["pricing"] = item["id"]
            self.ledger["pricing-plans"].append({"id": item["id"], "slug": pricing["slug"]})
            pricing["description"] = "E2E plan updated"
            self.request(
                "ADMIN-CONTENT-013", "update_pricing_plan_api_v1_admin_pricing_plans__entity_id__put", "Update pricing plan", "PUT",
                f"/api/v1/admin/pricing-plans/{item['id']}", kind="positive", expected={200}, headers=headers, body=pricing,
            )
            exam = {"title": f"{RUN_ID} exam", "slug": f"{slug_prefix}-exam", "description": "E2E exam", "mode": "ONLINE", "registration_starts_at": "2026-01-01T00:00:00Z", "registration_ends_at": "2027-01-01T00:00:00Z", "exam_starts_at": "2027-02-01T00:00:00Z", "exam_ends_at": "2027-02-01T02:00:00Z", "capacity": 10, "status": "REGISTRATION_OPEN", "pricing_plan_ids": [item["id"]]}
            eresp, eitem = self.request(
                "ADMIN-CONTENT-014", "create_exam_api_v1_admin_exams_post", "Create open exam linked to pricing", "POST",
                "/api/v1/admin/exams", kind="positive", expected={201}, headers=headers, body=exam,
            )
            if eresp and eresp.status_code == 201:
                self.created["exam"] = eitem["id"]
                self.ledger["exams"].append({"id": eitem["id"], "slug": exam["slug"]})
                exam["description"] = "E2E exam updated"
                self.request(
                    "ADMIN-CONTENT-015", "update_exam_api_v1_admin_exams__entity_id__put", "Update exam and preserve pricing relationship", "PUT",
                    f"/api/v1/admin/exams/{eitem['id']}", kind="positive", expected={200}, headers=headers, body=exam,
                )
            self.request(
                "ADMIN-CONTENT-NEG-002", "create_exam_api_v1_admin_exams_post", "Exam rejects nonexistent pricing-plan reference", "POST",
                "/api/v1/admin/exams", kind="negative", expected={422}, headers=headers,
                body={**exam, "slug": f"{slug_prefix}-invalid-exam", "pricing_plan_ids": [str(uuid.uuid4())]}, validate_contract=False,
            )

        gallery = {"title": f"{RUN_ID} gallery", "slug": f"{slug_prefix}-gallery", "description": "E2E gallery", "cover_image_id": image_id, "sort_order": -99999, "status": "PUBLISHED"}
        response, item = self.request(
            "ADMIN-CONTENT-016", "create_gallery_api_v1_admin_gallery_post", "Create published gallery album", "POST",
            "/api/v1/admin/gallery", kind="positive", expected={201}, headers=headers, body=gallery,
        )
        if response and response.status_code == 201:
            self.created["gallery"] = item["id"]
            self.created["gallery_slug"] = gallery["slug"]
            self.ledger["gallery"].append({"id": item["id"], "slug": gallery["slug"]})
            gallery["description"] = "E2E gallery updated"
            self.request(
                "ADMIN-CONTENT-017", "update_gallery_album_api_v1_admin_gallery__entity_id__put", "Update gallery album", "PUT",
                f"/api/v1/admin/gallery/{item['id']}", kind="positive", expected={200}, headers=headers, body=gallery,
            )
            if image_id:
                iresp, iitem = self.request(
                    "ADMIN-CONTENT-018", "create_gallery_item_api_v1_admin_gallery__album_id__items_post", "Create gallery item with uploaded media", "POST",
                    f"/api/v1/admin/gallery/{item['id']}/items", kind="positive", expected={201}, headers=headers,
                    body={"media_id": image_id, "title": RUN_ID, "description": "E2E item", "sort_order": 0},
                )
                if iresp and iresp.status_code == 201:
                    self.created["gallery_item"] = iitem["id"]
            else:
                self.blocked("create_gallery_item_api_v1_admin_gallery__album_id__items_post", "Gallery item with uploaded media", "Public media upload failed.")

        document_id = self.created.get("media_document")
        if document_id:
            sample = {"title": f"{RUN_ID} sample", "description": "E2E sample", "education_level": "E2E", "exam_year": 1405, "file_media_id": document_id, "cover_media_id": image_id, "sort_order": -99999, "status": "PUBLISHED"}
            response, item = self.request(
                "ADMIN-CONTENT-019", "create_sample_exam_api_v1_admin_sample_exams_post", "Create published sample exam with uploaded document", "POST",
                "/api/v1/admin/sample-exams", kind="positive", expected={201}, headers=headers, body=sample,
            )
            if response and response.status_code == 201:
                self.created["sample_exam"] = item["id"]
                self.ledger["sample-exams"].append({"id": item["id"]})
                sample["description"] = "E2E sample updated"
                self.request(
                    "ADMIN-CONTENT-020", "update_sample_exam_api_v1_admin_sample_exams__entity_id__put", "Update sample exam", "PUT",
                    f"/api/v1/admin/sample-exams/{item['id']}", kind="positive", expected={200}, headers=headers, body=sample,
                )
        else:
            for op in ["create_sample_exam_api_v1_admin_sample_exams_post", "update_sample_exam_api_v1_admin_sample_exams__entity_id__put"]:
                self.blocked(op, "Sample exam lifecycle with uploaded PDF", "Document media upload failed.")

    def admin_blog_workflow(self, headers: dict[str, str]) -> None:
        op_create = "create_blog_post_api_v1_admin_blog_post"
        slug = f"{RUN_ID.lower()}-blog"
        body = {
            "title": f"{RUN_ID} blog",
            "slug": slug,
            "summary": "E2E blog summary",
            "content_document": {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": RUN_ID}]}]},
            "cover_image_id": self.created.get("media_image"),
            "seo_title": f"{RUN_ID} SEO",
            "seo_description": "E2E SEO",
            "locale": "fa-IR",
        }
        response, item = self.request(
            "BLOG-ADMIN-001", op_create, "Create isolated draft blog post", "POST", "/api/v1/admin/blog",
            kind="positive", expected={201}, headers=headers, body=body,
        )
        if not response or response.status_code != 201:
            return
        post_id = item["id"]
        self.created["blog"] = post_id
        self.created["blog_slug"] = slug
        self.ledger["blog"].append({"id": post_id, "slug": slug})
        self.request(
            "BLOG-ADMIN-002", "get_blog_post_api_v1_admin_blog__post_id__get", "Read draft blog detail", "GET",
            f"/api/v1/admin/blog/{post_id}", kind="positive", expected={200}, headers=headers,
        )
        self.request(
            "BLOG-PUBLIC-DRAFT", "get_blog_post_api_v1_public_blog__slug__get", "Draft blog is not public", "GET",
            f"/api/v1/public/blog/{slug}", kind="negative", expected={404}, validate_contract=False,
        )
        self.request(
            "BLOG-ADMIN-NEG-001", op_create, "Duplicate blog slug is rejected", "POST", "/api/v1/admin/blog",
            kind="negative", expected={409}, headers=headers, body=body, validate_contract=False,
        )
        self.request(
            "BLOG-ADMIN-NEG-002", op_create, "Invalid blog slug format is rejected", "POST", "/api/v1/admin/blog",
            kind="negative", expected={422}, headers=headers, body={**body, "slug": "INVALID SLUG"},
        )
        updated_doc = {"type": "doc", "content": [{"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Updated E2E"}]}]}
        self.request(
            "BLOG-ADMIN-003", "update_blog_post_api_v1_admin_blog__post_id__patch", "Update draft blog content", "PATCH",
            f"/api/v1/admin/blog/{post_id}", kind="positive", expected={200}, headers=headers,
            body={"title": f"{RUN_ID} blog updated", "content_document": updated_doc},
        )
        response, published = self.request(
            "BLOG-ADMIN-004", "publish_blog_post_api_v1_admin_blog__post_id__publish_post", "Publish blog", "POST",
            f"/api/v1/admin/blog/{post_id}/publish", kind="positive", expected={200}, headers=headers,
        )
        if response and response.status_code == 200 and published.get("status") == "PUBLISHED":
            self.coverage["publish_blog_post_api_v1_admin_blog__post_id__publish_post"]["integration"] = "PASS"

    def admin_reads(self, headers: dict[str, str]) -> None:
        get_ops = [
            ("list_blog_posts_api_v1_admin_blog_get", "/api/v1/admin/blog", {"status": "PUBLISHED"}),
            ("list_posts_api_v1_admin_posts_get", "/api/v1/admin/posts", {"kind": "NEWS"}),
            ("list_banners_api_v1_admin_banners_get", "/api/v1/admin/banners", {}),
            ("list_honor_categories_api_v1_admin_honor_categories_get", "/api/v1/admin/honor-categories", {}),
            ("list_honors_api_v1_admin_honors_get", "/api/v1/admin/honors", {}),
            ("list_staff_api_v1_admin_staff_get", "/api/v1/admin/staff", {}),
            ("list_pricing_api_v1_admin_pricing_plans_get", "/api/v1/admin/pricing-plans", {}),
            ("list_exams_api_v1_admin_exams_get", "/api/v1/admin/exams", {}),
            ("list_sample_exams_api_v1_admin_sample_exams_get", "/api/v1/admin/sample-exams", {}),
            ("list_gallery_api_v1_admin_gallery_get", "/api/v1/admin/gallery", {}),
            ("list_contact_requests_api_v1_admin_contact_requests_get", "/api/v1/admin/contact-requests", {}),
            ("build_status_api_v1_admin_site_build_status_get", "/api/v1/admin/site-build/status", {}),
            ("build_history_api_v1_admin_site_build_history_get", "/api/v1/admin/site-build/history", {}),
            ("list_registrations_api_v1_admin_registrations_get", "/api/v1/admin/registrations", {}),
        ]
        for index, (op, path, params) in enumerate(get_ops, 1):
            self.request(
                f"ADMIN-READ-{index:03d}", op, "Authenticated admin list/read", "GET", path,
                kind="positive", expected={200}, headers=headers, params=params,
            )

    def site_build_workflow(self) -> None:
        if not self.admin_headers:
            return
        rebuild_op = "manual_rebuild_api_v1_admin_site_build_rebuild_post"
        status_op = "build_status_api_v1_admin_site_build_status_get"
        history_op = "build_history_api_v1_admin_site_build_history_get"
        response, initial = self.request(
            "BUILD-001", rebuild_op, "Request manual site rebuild", "POST", "/api/v1/admin/site-build/rebuild",
            kind="positive", expected={202}, headers=self.admin_headers,
        )
        if not response or response.status_code != 202:
            return
        request_id = initial.get("latest_request_id")
        transitions = [initial.get("state")]
        terminal = initial.get("state") in {"UP_TO_DATE", "FAILED", "NOT_CONFIGURED"}
        latest = initial
        for attempt in range(3):
            if terminal:
                break
            time.sleep(2)
            sresp, latest = self.request(
                f"BUILD-POLL-{attempt+1:03d}", status_op, "Poll site build at bounded cadence", "GET",
                "/api/v1/admin/site-build/status", kind="positive", expected={200}, headers=self.admin_headers,
            )
            if not sresp or sresp.status_code != 200:
                break
            transitions.append(latest.get("state"))
            terminal = latest.get("state") in {"UP_TO_DATE", "FAILED", "NOT_CONFIGURED"}
        response, history = self.request(
            "BUILD-002", history_op, "Build history contains triggered request", "GET",
            "/api/v1/admin/site-build/history", kind="positive", expected={200}, headers=self.admin_headers,
            params={"page": 1, "page_size": 100},
        )
        present = bool(
            response
            and response.status_code == 200
            and request_id
            and any(item.get("id") == request_id for item in history.get("items", []))
        )
        self.coverage[rebuild_op]["integration"] = "PASS" if present else "FAIL"
        self.coverage[history_op]["integration"] = "PASS" if present else "FAIL"
        self.environment["site_build_transitions"] = transitions
        self.environment["site_build_terminal_observed"] = terminal

    def archive_cleanup(self) -> None:
        if not self.admin_headers:
            return
        archive_op = "archive_resource_api_v1_admin__resource___entity_id__delete"
        # Dedicated blog archive first, followed by generic resource archive/delete operations.
        if self.created.get("blog"):
            blog_id = self.created["blog"]
            response, archived = self.request(
                "CLEANUP-BLOG-001", "archive_blog_post_api_v1_admin_blog__post_id__archive_post",
                "Archive created blog", "POST", f"/api/v1/admin/blog/{blog_id}/archive",
                kind="positive", expected={200}, headers=self.admin_headers,
            )
            if response and response.status_code == 200:
                self.ledger["blog"][0]["cleanup_state"] = archived.get("status")
                self.request(
                    "CLEANUP-BLOG-002", "get_blog_post_api_v1_public_blog__slug__get",
                    "Archived blog disappears publicly", "GET", f"/api/v1/public/blog/{self.created['blog_slug']}",
                    kind="negative", expected={404}, validate_contract=False,
                )
        targets = [
            ("posts", "news", "posts"),
            ("posts", "announcement", "posts"),
            ("banners", "banner", "banners"),
            ("honors", "honor", "honors"),
            ("honor-categories", "honor_category", "honor-categories"),
            ("staff", "staff", "staff"),
            ("exams", "exam", "exams"),
            ("pricing-plans", "pricing", "pricing-plans"),
            ("sample-exams", "sample_exam", "sample-exams"),
            ("gallery", "gallery", "gallery"),
        ]
        archived_targets: list[tuple[str, str]] = []
        for index, (resource, key, ledger_key) in enumerate(targets, 1):
            entity_id = self.created.get(key)
            if not entity_id:
                continue
            response, _ = self.request(
                f"CLEANUP-{index:03d}", archive_op, f"Archive/delete created {resource} resource", "DELETE",
                f"/api/v1/admin/{resource}/{entity_id}", kind="positive", expected={204}, headers=self.admin_headers,
            )
            if response and response.status_code == 204:
                archived_targets.append((resource, entity_id))
                for row in self.ledger.get(ledger_key, []):
                    if row.get("id") == entity_id:
                        row["cleanup_state"] = "ARCHIVED_OR_INACTIVE"
        if archived_targets:
            resource, entity_id = archived_targets[0]
            self.request(
                "CLEANUP-REPLAY", archive_op, "Repeat archive is replay-safe", "DELETE",
                f"/api/v1/admin/{resource}/{entity_id}", kind="positive", expected={204}, headers=self.admin_headers,
            )
        self.request(
            "CLEANUP-NEG-001", archive_op, "Unsupported archive resource is rejected", "DELETE",
            f"/api/v1/admin/unsupported/{uuid.uuid4()}", kind="negative", expected={404}, headers=self.admin_headers,
            validate_contract=False,
        )
        self.request(
            "CLEANUP-NEG-002", archive_op, "Malformed archive UUID is rejected", "DELETE",
            "/api/v1/admin/banners/not-a-uuid", kind="negative", expected={422}, headers=self.admin_headers,
        )
        # Verify the key slug-addressable resources are no longer public.
        for test_id, op_id, path in [
            ("CLEANUP-PUBLIC-NEWS", "news_detail_api_v1_public_news__slug__get", f"/api/v1/public/news/{self.created.get('news_slug', RUN_ID)}"),
            ("CLEANUP-PUBLIC-ANN", "announcement_detail_api_v1_public_announcements__slug__get", f"/api/v1/public/announcements/{self.created.get('announcement_slug', RUN_ID)}"),
            ("CLEANUP-PUBLIC-GALLERY", "gallery_detail_api_v1_public_gallery__slug__get", f"/api/v1/public/gallery/{self.created.get('gallery_slug', RUN_ID)}"),
        ]:
            self.request(test_id, op_id, "Archived resource is no longer publicly addressable", "GET", path, kind="negative", expected={404}, validate_contract=False)

    def tenant_checks(self) -> None:
        site_op = "site_bootstrap_api_v1_public_site_get"
        response, _ = self.request("TENANT-001", site_op, "Unknown Host does not fall back to tenant", "GET", "/api/v1/public/site", kind="negative", expected={404}, headers={"Host": "unauthorized.invalid"}, validate_contract=False)
        if response and response.status_code == 404:
            self.environment["unknown_host_rejected"] = True
        self.environment["cross_tenant_positive_test"] = "BLOCKED: no second explicitly authorized tenant/domain or credentials were available"

    def reliability(self) -> None:
        op = "live_health_live_get"
        statuses = []
        for i in range(3):
            response, _ = self.request(f"RELIABILITY-{i+1:03d}", op, "Repeated health read remains stable", "GET", "/health/live", kind="positive", expected={200})
            statuses.append(response.status_code if response else None)
        self.environment["health_repeat_statuses"] = statuses

    def cleanup(self) -> dict[str, Any]:
        remaining = []
        for kind, rows in self.ledger.items():
            for row in rows:
                state = row.get("cleanup_state") or row.get("status")
                if state not in {"ARCHIVED", "ARCHIVED_OR_INACTIVE", "CANCELLED", "CLOSED"}:
                    remaining.append({"kind": kind, **row})
        return {
            "attempted": bool(self.ledger),
            "result": "PASS" if not remaining else "PARTIAL",
            "reason": "All API-cleanable content was archived/inactivated; media has no delete operation and contact requests are retained as CLOSED." if remaining else "All created resources reached an API-supported cleanup state.",
            "remaining_resources": redact(dict(self.ledger)),
            "not_cleanable": redact(remaining),
        }

    def finalize(self) -> None:
        # Every operation must have a test record or an explicit blocker.
        recorded = {t["operation_id"] for t in self.tests}
        for op_id in sorted(set(OPS) - recorded):
            self.blocked(op_id, "Coverage reconciliation", "Operation had no safe executable prerequisite in this run.")
        missing = sorted(set(OPS) - {t["operation_id"] for t in self.tests})
        counts = Counter(row["result"] for row in self.coverage.values())
        cleanup = self.cleanup()
        finished = datetime.now(UTC)
        result = {
            "run_id": RUN_ID,
            "base_url": BASE_URL,
            "started": STARTED.isoformat(),
            "finished": finished.isoformat(),
            "total_operations": len(OPS),
            "operations_exercised": len(OPS) - counts.get("NOT_APPLICABLE", 0),
            "passed": counts.get("PASS", 0),
            "failed": counts.get("FAIL", 0),
            "blocked": counts.get("BLOCKED", 0),
            "not_applicable": counts.get("NOT_APPLICABLE", 0),
            "overall_result": "PASS" if counts.get("FAIL", 0) == 0 and counts.get("BLOCKED", 0) == 0 else "FAIL",
            "environment": self.environment,
            "deployed_openapi_matches_supplied": self.remote_openapi_equal,
            "operation_coverage": list(self.coverage.values()),
            "tests": self.tests,
            "failures": self.findings,
            "contract_violations": self.contract_violations,
            "resource_ledger": redact(dict(self.ledger)),
            "cleanup": cleanup,
            "missing_operations": missing,
        }
        (OUT / "results.raw.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps({k: result[k] for k in ("run_id", "total_operations", "operations_exercised", "passed", "failed", "blocked", "overall_result", "missing_operations")}, indent=2))

    def run(self) -> None:
        try:
            self.preflight()
            self.authentication()
            self.admin_surface()
            public_data = self.public_reads()
            self.contact_request()
            self.media_public(public_data)
            self.registration(public_data)
            self.callback_negatives()
            self.site_build_workflow()
            self.tenant_checks()
            self.reliability()
            self.archive_cleanup()
        finally:
            self.finalize()
            self.client.close()


if __name__ == "__main__":
    Runner().run()
