#!/usr/bin/env python3
"""Finish token-type misuse and rotation checks without persisting secrets."""

from __future__ import annotations

import getpass
import importlib.util
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
data = json.loads((HERE / "results.raw.json").read_text())
spec = importlib.util.spec_from_file_location("kanoon_live_e2e_auth", HERE / "live_e2e.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.RUN_ID = data["run_id"]
module.STARTED = datetime.fromisoformat(data["started"])
runner = module.Runner()
runner.tests = data["tests"]
runner.coverage = {row["operation_id"]: row for row in data["operation_coverage"]}
runner.ledger = defaultdict(list, data["resource_ledger"])
runner.environment = data["environment"]
runner.remote_openapi_equal = data["deployed_openapi_matches_supplied"]
runner.findings = data["failures"]

username = getpass.getpass("Admin username (hidden): ")
password = getpass.getpass("Admin password (hidden): ")
response, pair = runner.request(
    "AUTH-EXTRA-001", "tenant_login_api_v1_admin_auth_login_post", "Login for token-type checks",
    "POST", "/api/v1/admin/auth/login", kind="positive", expected={200},
    body={"email": username, "password": password},
)
if response and response.status_code == 200:
    access = pair["access_token"]
    refresh = pair["refresh_token"]
    runner.request(
        "AUTH-EXTRA-002", "list_banners_api_v1_admin_banners_get", "Refresh token cannot be used as bearer access token",
        "GET", "/api/v1/admin/banners", kind="negative", expected={401},
        headers={"Authorization": f"Bearer {refresh}"}, validate_contract=False,
    )
    runner.request(
        "AUTH-EXTRA-003", "tenant_refresh_api_v1_admin_auth_refresh_post", "Access token cannot be used as refresh token",
        "POST", "/api/v1/admin/auth/refresh", kind="negative", expected={401},
        body={"refresh_token": access}, validate_contract=False,
    )
    rotated_response, rotated = runner.request(
        "AUTH-EXTRA-004", "tenant_refresh_api_v1_admin_auth_refresh_post", "Valid refresh rotates successfully",
        "POST", "/api/v1/admin/auth/refresh", kind="positive", expected={200}, body={"refresh_token": refresh},
    )
    if rotated_response and rotated_response.status_code == 200:
        runner.request(
            "AUTH-EXTRA-005", "list_banners_api_v1_admin_banners_get", "Rotated access token reaches protected API",
            "GET", "/api/v1/admin/banners", kind="positive", expected={200},
            headers={"Authorization": f"Bearer {rotated['access_token']}"},
        )
        runner.request(
            "AUTH-EXTRA-006", "tenant_refresh_api_v1_admin_auth_refresh_post", "Old refresh reuse is detected",
            "POST", "/api/v1/admin/auth/refresh", kind="negative", expected={401}, body={"refresh_token": refresh},
            validate_contract=False,
        )
        runner.request(
            "AUTH-EXTRA-007", "tenant_refresh_api_v1_admin_auth_refresh_post", "Refresh family is revoked after reuse",
            "POST", "/api/v1/admin/auth/refresh", kind="negative", expected={401},
            body={"refresh_token": rotated["refresh_token"]}, validate_contract=False,
        )
runner.finalize()
runner.client.close()
