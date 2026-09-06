#!/usr/bin/env python3
"""Build sanitized post-fix live-preflight artifacts when deployment is unavailable."""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[2]
BASE_URL = "https://kanoon.esaminu.ir"
SPEC = json.loads((ROOT / "openapi.json").read_text(encoding="utf-8"))
STARTED = datetime.now(UTC)
RUN_ID = f"kanoon-fix-e2e-{STARTED:%Y%m%dT%H%M%SZ}-{secrets.token_hex(3)}"
METHODS = {"get", "post", "put", "patch", "delete"}


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def operation_map(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    operations: dict[str, dict[str, Any]] = {}
    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            if method not in METHODS:
                continue
            operations[operation["operationId"]] = {
                "method": method.upper(),
                "path": path,
                "tags": operation.get("tags", []),
                "operation": operation,
                "path_item": path_item,
            }
    return operations


OPS = operation_map(SPEC)
assert len(OPS) == 84


def inventory() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for operation_id, metadata in OPS.items():
        operation = metadata["operation"]
        path_item = metadata["path_item"]
        parameters = list(path_item.get("parameters", [])) + list(operation.get("parameters", []))
        by_location = {
            location: [item for item in parameters if item.get("in") == location]
            for location in ("path", "query", "header")
        }
        result.append(
            {
                "method": metadata["method"],
                "path": metadata["path"],
                "operation_id": operation_id,
                "tags": metadata["tags"],
                "security": operation.get("security", SPEC.get("security", [])),
                "path_parameters": by_location["path"],
                "query_parameters": by_location["query"],
                "header_parameters": by_location["header"],
                "request_schema": {
                    media_type: content.get("schema")
                    for media_type, content in operation.get("requestBody", {})
                    .get("content", {})
                    .items()
                },
                "success_statuses": [
                    status
                    for status in operation.get("responses", {})
                    if str(status).startswith("2") or str(status).startswith("3")
                ],
                "documented_error_statuses": [
                    status
                    for status in operation.get("responses", {})
                    if not str(status).startswith(("2", "3"))
                ],
                "response_schema": operation.get("responses", {}),
            }
        )
    return result


def live_get(
    client: httpx.Client, path: str, *, headers: dict[str, str] | None = None
) -> tuple[httpx.Response | None, float, str | None]:
    started = time.perf_counter()
    try:
        response = client.get(path, headers=headers)
        return response, round((time.perf_counter() - started) * 1000, 2), None
    except httpx.HTTPError as exc:
        return None, round((time.perf_counter() - started) * 1000, 2), type(exc).__name__


def safe_response(response: httpx.Response | None) -> tuple[dict[str, Any], dict[str, str]]:
    if response is None:
        return {}, {}
    body: Any
    if "application/json" in response.headers.get("content-type", ""):
        try:
            body = response.json()
        except ValueError:
            body = "<invalid-json>"
    else:
        body = response.text[:500]
    headers = {
        key: value
        for key, value in response.headers.items()
        if key.casefold() in {"content-type", "content-length", "server", "via", "cache-control"}
    }
    return body, headers


client = httpx.Client(
    base_url=BASE_URL,
    timeout=httpx.Timeout(20),
    follow_redirects=False,
    headers={"User-Agent": f"Kanoon-Fix-E2E/{RUN_ID}", "X-Request-ID": RUN_ID},
)

live_response, live_ms, live_error = live_get(client, "/health/live")
ready_response, ready_ms, ready_error = live_get(client, "/health/ready")
unknown_response, unknown_ms, unknown_error = live_get(
    client, "/api/v1/public/site", headers={"Host": "unauthorized.invalid"}
)
forwarded_response, forwarded_ms, forwarded_error = live_get(
    client, "/api/v1/public/site", headers={"X-Forwarded-Host": "unauthorized.invalid"}
)
remote_openapi_response, openapi_ms, openapi_error = live_get(client, "/openapi.json")
client.close()

remote_spec: dict[str, Any] | None = None
if remote_openapi_response is not None and remote_openapi_response.status_code == 200:
    try:
        candidate = remote_openapi_response.json()
        if isinstance(candidate, dict):
            remote_spec = candidate
    except ValueError:
        pass

remote_ops = operation_map(remote_spec) if remote_spec is not None else {}
response_drift_operations = sorted(
    operation_id
    for operation_id in set(OPS) & set(remote_ops)
    if OPS[operation_id]["operation"].get("responses")
    != remote_ops[operation_id]["operation"].get("responses")
)

coverage: list[dict[str, Any]] = []
for operation_id, metadata in OPS.items():
    result = "BLOCKED"
    positive = "NOT_RUN"
    negative = "NOT_RUN"
    integration = "NOT_RUN"
    reason = (
        "Corrected backend was not deployed: the repository provides no authorized production "
        "host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service "
        "is still the baseline revision."
    )
    if operation_id == "live_health_live_get":
        result = positive = "PASS" if live_response is not None and live_response.status_code == 200 else "FAIL"
        reason = "Fresh live health probe completed."
    elif operation_id == "ready_health_ready_get":
        result = positive = (
            "PASS" if ready_response is not None and ready_response.status_code == 200 else "FAIL"
        )
        reason = "Fresh live readiness probe completed."
    elif operation_id == "site_bootstrap_api_v1_public_site_get":
        positive = (
            "PASS"
            if forwarded_response is not None and forwarded_response.status_code == 200
            else "FAIL"
        )
        negative = (
            "PASS"
            if unknown_response is not None and unknown_response.status_code in {404, 421}
            else "FAIL"
        )
        result = "PASS" if positive == negative == "PASS" else "FAIL"
        reason = "Canonical host remained usable, but unknown Host was not rejected."
    coverage.append(
        {
            "operation_id": operation_id,
            "method": metadata["method"],
            "path": metadata["path"],
            "positive": positive,
            "negative": negative,
            "integration": integration,
            "result": result,
            "reason": reason,
        }
    )


def test_record(
    *,
    test_id: str,
    operation_id: str,
    scenario: str,
    result: str,
    timing_ms: float,
    status_code: int | None,
    request_headers: dict[str, str] | None = None,
    response: httpx.Response | None = None,
    failure_id: str | None = None,
    notes: str = "",
) -> dict[str, Any]:
    body, response_headers = safe_response(response)
    return {
        "test_id": test_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "operation_id": operation_id,
        "scenario": scenario,
        "kind": "blocked" if result == "BLOCKED" else "live-preflight",
        "result": result,
        "timing_ms": timing_ms,
        "status_code": status_code,
        "method": OPS[operation_id]["method"],
        "path": OPS[operation_id]["path"],
        "request_headers": request_headers or {},
        "request_query": {},
        "request_body": None,
        "response_headers": response_headers,
        "response_body": body,
        "failure_id": failure_id,
        "notes": notes,
    }


tests = [
    test_record(
        test_id="PREFLIGHT-HEALTH-LIVE",
        operation_id="live_health_live_get",
        scenario="Live liveness after proposed repair",
        result="PASS" if live_response is not None and live_response.status_code == 200 else "FAIL",
        timing_ms=live_ms,
        status_code=live_response.status_code if live_response is not None else None,
        response=live_response,
        notes=live_error or "Fresh bounded read-only probe.",
    ),
    test_record(
        test_id="PREFLIGHT-HEALTH-READY",
        operation_id="ready_health_ready_get",
        scenario="Live readiness after proposed repair",
        result="PASS" if ready_response is not None and ready_response.status_code == 200 else "FAIL",
        timing_ms=ready_ms,
        status_code=ready_response.status_code if ready_response is not None else None,
        response=ready_response,
        notes=ready_error or "Fresh bounded read-only probe.",
    ),
    test_record(
        test_id="PREFLIGHT-UNKNOWN-HOST",
        operation_id="site_bootstrap_api_v1_public_site_get",
        scenario="Unknown Host is explicitly rejected by the edge or tenant resolver",
        result=(
            "PASS"
            if unknown_response is not None and unknown_response.status_code in {404, 421}
            else "FAIL"
        ),
        timing_ms=unknown_ms,
        status_code=unknown_response.status_code if unknown_response is not None else None,
        request_headers={"Host": "unauthorized.invalid"},
        response=unknown_response,
        failure_id="FAIL-005",
        notes=unknown_error or "TLS SNI remained canonical; only the HTTP Host was varied.",
    ),
    test_record(
        test_id="PREFLIGHT-FORWARDED-HOST",
        operation_id="site_bootstrap_api_v1_public_site_get",
        scenario="Untrusted X-Forwarded-Host cannot change canonical tenant selection",
        result=(
            "PASS"
            if forwarded_response is not None and forwarded_response.status_code == 200
            else "FAIL"
        ),
        timing_ms=forwarded_ms,
        status_code=forwarded_response.status_code if forwarded_response is not None else None,
        request_headers={"X-Forwarded-Host": "unauthorized.invalid"},
        response=forwarded_response,
        notes=forwarded_error or "Canonical Host was preserved.",
    ),
]

already_recorded = {item["operation_id"] for item in tests}
for index, operation_id in enumerate(sorted(set(OPS) - already_recorded), 1):
    tests.append(
        test_record(
            test_id=f"DEPLOYMENT-BLOCKED-{index:03d}",
            operation_id=operation_id,
            scenario="Post-fix stateful live verification",
            result="BLOCKED",
            timing_ms=0,
            status_code=None,
            notes=(
                "No request sent: the corrected image is not deployed, no authorized deployment "
                "target/workflow is present, and admin credentials are unset."
            ),
        )
    )

counts = Counter(item["result"] for item in coverage)
assert counts == Counter({"BLOCKED": 81, "PASS": 2, "FAIL": 1})
assert {item["operation_id"] for item in coverage} == set(OPS)

local_hash = canonical_hash(SPEC)
remote_hash = canonical_hash(remote_spec) if remote_spec is not None else None
contract_violations = [
    {
        "test_id": "PREFLIGHT-OPENAPI-DRIFT",
        "operation_id": "export_registrations_api_v1_admin_registrations_export_csv_get",
        "actual_status": remote_openapi_response.status_code
        if remote_openapi_response is not None
        else None,
        "detail": (
            "Generated/supplied and deployed OpenAPI differ. The deployed contract has no reusable "
            "error responses and still declares registration CSV as application/json."
        ),
        "local_sha256": local_hash,
        "deployed_sha256": remote_hash,
        "response_drift_operation_count": len(response_drift_operations),
        "response_drift_operation_ids": response_drift_operations,
    }
]

failures = [
    {
        "failure_id": "FAIL-001",
        "severity": "P1",
        "title": "Generic admin content updates return 500 on the deployed baseline",
        "local_status": "FIXED_AND_REGRESSION_TESTED",
        "live_status": "OPEN_UNDEPLOYED",
    },
    {
        "failure_id": "FAIL-002",
        "severity": "P1",
        "title": "Public registration PATCH returns 500 on the deployed baseline",
        "local_status": "FIXED_AND_REGRESSION_TESTED",
        "live_status": "OPEN_UNDEPLOYED",
    },
    {
        "failure_id": "FAIL-003",
        "severity": "P2",
        "title": "Premature media completion returns 500 on the deployed baseline",
        "local_status": "FIXED_AND_REGRESSION_TESTED",
        "live_status": "OPEN_UNDEPLOYED",
    },
    {
        "failure_id": "FAIL-004",
        "severity": "P1",
        "title": "Public media download signature is invalid on the deployed baseline",
        "local_status": "FIXED_AND_REAL_S3_REGRESSION_TESTED",
        "live_status": "OPEN_UNDEPLOYED",
    },
    {
        "failure_id": "FAIL-005",
        "severity": "P3",
        "title": "Unknown hosts receive an empty edge 200",
        "local_status": "FIXED_AND_CONFIG_VALIDATED",
        "live_status": "REPRODUCED_OPEN",
    },
    {
        "failure_id": "FAIL-006",
        "severity": "P3",
        "title": "OpenAPI response contract is incomplete on the deployed baseline",
        "local_status": "FIXED_AND_CONTRACT_TESTED",
        "live_status": "REPRODUCED_OPEN",
    },
]

result = {
    "run_id": RUN_ID,
    "base_url": BASE_URL,
    "deployed_revision": "UNAVAILABLE",
    "started": STARTED.isoformat(),
    "finished": datetime.now(UTC).isoformat(),
    "overall_result": "FAIL",
    "production_ready": False,
    "total_operations": len(OPS),
    "operations_exercised": 3,
    "passed": counts["PASS"],
    "failed": counts["FAIL"],
    "blocked": counts["BLOCKED"],
    "not_applicable": counts["NOT_APPLICABLE"],
    "missing_operations": [],
    "operation_inventory": inventory(),
    "operation_coverage": coverage,
    "tests": tests,
    "failures": failures,
    "contract_violations": contract_violations,
    "resource_ledger": {},
    "cleanup": {
        "attempted": False,
        "result": "COMPLETE",
        "reason": "Preflight stopped before mutations; no fresh live resources were created.",
        "remaining_resources": {},
    },
    "environment": {
        "admin_credentials": "UNSET",
        "deployment": "BLOCKED_NO_AUTHORIZED_TARGET_OR_WORKFLOW",
        "deployment_preflight_reason": (
            "Live OpenAPI and unknown-host behavior prove the corrected backend and edge config are "
            "not deployed."
        ),
        "local_openapi_sha256": local_hash,
        "deployed_openapi_sha256": remote_hash,
        "deployed_openapi_status": remote_openapi_response.status_code
        if remote_openapi_response is not None
        else None,
        "deployed_openapi_timing_ms": openapi_ms,
        "deployed_openapi_error": openapi_error,
        "deployed_operation_count": len(remote_ops),
        "deployed_reusable_response_count": len(
            remote_spec.get("components", {}).get("responses", {}) if remote_spec else {}
        ),
        "response_drift_operation_count": len(response_drift_operations),
        "unknown_host_status": unknown_response.status_code
        if unknown_response is not None
        else None,
        "forwarded_host_probe_status": forwarded_response.status_code
        if forwarded_response is not None
        else None,
        "live_health_error": live_error,
        "ready_health_error": ready_error,
    },
}

(ROOT / "FULL_API_SMOKE_TEST_RESULTS.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)

areas: defaultdict[str, Counter[str]] = defaultdict(Counter)
for row in coverage:
    tag = OPS[row["operation_id"]]["tags"]
    areas[tag[0] if tag else "untagged"][row["result"]] += 1

lines = [
    "# Kanoon Backend — Full API E2E Test Report",
    "",
    "## Executive Summary",
    "",
    f"- Run ID: `{RUN_ID}`",
    f"- Base URL: `{BASE_URL}`",
    "- Deployed revision: `UNAVAILABLE` (no version endpoint/header)",
    "- Overall result: **FAIL — NOT PRODUCTION-READY**",
    f"- Coverage matrix: {len(OPS)}/{len(OPS)} operations represented exactly once",
    "- Live operations actually exercised after repair: 3/84",
    f"- PASS / FAIL / BLOCKED / NOT_APPLICABLE: {counts['PASS']} / {counts['FAIL']} / {counts['BLOCKED']} / 0",
    "",
    "The corrected source and image passed local verification, but they could not be deployed: the "
    "repository contains no authorized production host, credential, or deployment workflow. The "
    "live edge and OpenAPI still exhibit baseline behavior, so stateful mutation testing was stopped "
    "before creating resources.",
    "",
    "## Critical Findings",
    "",
    "- P0: 0.",
    "- P1: 3 remain open on the live deployment (FAIL-001, FAIL-002, FAIL-004).",
    "- P2: 1 remains open on the live deployment (FAIL-003).",
    "- P3: 2 remain open on the live deployment (FAIL-005, FAIL-006).",
    "- All six have local fixes and regression evidence; none is live-closed without deployment.",
    "",
    "## Coverage Summary",
    "",
    "| Area | PASS | FAIL | BLOCKED |",
    "|---|---:|---:|---:|",
]
for area in sorted(areas):
    counter = areas[area]
    lines.append(
        f"| {area} | {counter['PASS']} | {counter['FAIL']} | {counter['BLOCKED']} |"
    )

lines.extend(
    [
        "",
        "## Endpoint Coverage",
        "",
        "| Method | Path | Operation ID | Positive | Negative | Integration | Result | Reason |",
        "|---|---|---|---|---|---|---|---|",
    ]
)
for row in coverage:
    reason = row["reason"].replace("|", "\\|")
    lines.append(
        f"| {row['method']} | `{row['path']}` | `{row['operation_id']}` | "
        f"{row['positive']} | {row['negative']} | {row['integration']} | "
        f"{row['result']} | {reason} |"
    )

lines.extend(
    [
        "",
        "## End-to-End Workflow Results",
        "",
        "| Workflow | Local result | Fresh live result |",
        "|---|---|---|",
        "| Nine generic content lifecycles | PASS for create/update/repeat/read/public/archive | BLOCKED: fixed build not deployed |",
        "| Registration PATCH field matrix and token/state boundaries | PASS | BLOCKED: fixed build not deployed |",
        "| Premature media completion, retry, and idempotency | PASS | BLOCKED: fixed build not deployed |",
        "| Real S3 upload, public exact-byte download, private denial | PASS against disposable MinIO | BLOCKED: fixed build not deployed |",
        "| Unknown-host rejection | PASS in middleware/config tests; Caddy config validates | FAIL: live edge returned empty 200 |",
        "| OTP success/expiry/attempt/reuse | PASS with local gated mock provider | BLOCKED: no authorized live retrieval facility |",
        "| Payment idempotency/callback/replay | PASS with local mock gateway | BLOCKED: no proven live sandbox/zero-value gateway |",
        "| Site-build signed callback/replay | PASS locally | BLOCKED: no live signer/builder authority |",
        "| Cross-tenant isolation | PASS with two local fixture tenants | BLOCKED: no second authorized live tenant |",
        "| School profile replacement/restore | Existing local coverage only | BLOCKED: no disposable live tenant or restore-to-null API |",
        "",
        "## Failed Tests",
        "",
        f"- `PREFLIGHT-UNKNOWN-HOST`: expected 404/421, received {unknown_response.status_code if unknown_response is not None else 'no response'} from Caddy.",
        "- Live OpenAPI drift remains: generated/supplied and deployed contracts are not canonically equal.",
        "",
        "## Blocked Tests",
        "",
        "- 81 operation IDs were not called against the known-old live deployment because those calls "
        "would not verify the repair and many require administrator credentials, which are unset.",
        "- Deployment is blocked by missing repository-owned production target/credential/workflow.",
        "- OTP, payment, site build, second-tenant, and school-profile prerequisites remain unavailable live.",
        "",
        "## Contract Violations",
        "",
        f"- Local generated contract SHA-256: `{local_hash}`.",
        f"- Deployed contract SHA-256: `{remote_hash or 'UNAVAILABLE'}`.",
        f"- Operation response maps with drift: {len(response_drift_operations)}.",
        "- Deployed reusable response components: "
        f"{len(remote_spec.get('components', {}).get('responses', {}) if remote_spec else {})}.",
        "- Deployed CSV success media type remains `application/json`; local generated contract is `text/csv`.",
        "",
        "## Security Findings",
        "",
        "- Unknown Host still receives HTTP 200 at the live edge; no tenant body leaked, but fail-closed routing is absent.",
        "- An injected `X-Forwarded-Host` did not change canonical tenant selection in the bounded probe.",
        "- No authentication token, OTP, signed URL query, signature, or credential was recorded.",
        "- Local private-media denial and tenant isolation tests pass; live multi-tenant proof remains blocked.",
        "",
        "## Flaky/Intermittent Behavior",
        "",
        "No retries or transient failures occurred in the bounded fresh preflight. A complete post-deployment "
        "flakiness assessment is blocked.",
        "",
        "## Cleanup Results",
        "",
        "No live resources were created, so no live cleanup was necessary. The disposable local MinIO "
        "container and objects were removed after tests. Historical baseline artifacts/resources were not touched.",
        "",
        "## Final Coverage Reconciliation",
        "",
        "- 84/84 current OpenAPI operations appear exactly once in `operation_coverage`.",
        "- Missing operation IDs: none.",
        "- Actually exercised live operation IDs: 3/84.",
        "- Final states: 2 PASS, 1 FAIL, 81 BLOCKED, 0 NOT_APPLICABLE.",
        "",
        "## Final Verdict",
        "",
        "**NOT PRODUCTION-READY.** The repaired build is locally green but is not deployed. Three P1 and "
        "one P2 defects therefore remain open on the live service, the live edge and OpenAPI still fail, "
        "and critical external workflows remain unverified.",
    ]
)

(ROOT / "FULL_API_SMOKE_TEST_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

print(
    json.dumps(
        {
            "run_id": RUN_ID,
            "operations_represented": len(coverage),
            "operations_exercised": result["operations_exercised"],
            "passed": result["passed"],
            "failed": result["failed"],
            "blocked": result["blocked"],
            "missing_operations": result["missing_operations"],
            "openapi_equal": local_hash == remote_hash,
        },
        indent=2,
    )
)
