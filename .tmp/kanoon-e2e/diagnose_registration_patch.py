#!/usr/bin/env python3
"""Isolate which valid registration PATCH field triggers the deployed 500."""

from __future__ import annotations

import getpass
import importlib.util
import json
import random
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
data = json.loads((HERE / "results.raw.json").read_text())
spec = importlib.util.spec_from_file_location("kanoon_live_e2e_diag", HERE / "live_e2e.py")
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
response, token_pair = runner.request(
    "AUTH-DIAG-001", "tenant_login_api_v1_admin_auth_login_post", "Authenticate registration PATCH diagnostic",
    "POST", "/api/v1/admin/auth/login", kind="positive", expected={200},
    body={"email": username, "password": password},
)
if not response or response.status_code != 200:
    runner.finalize()
    raise SystemExit("Authentication failed")
runner.admin_headers = {"Authorization": f"Bearer {token_pair['access_token']}"}

slug = f"{module.RUN_ID.lower()}-patch-diag"
exam_body = {
    "title": f"{module.RUN_ID} PATCH diagnostic exam",
    "slug": slug,
    "description": "Field isolation only",
    "mode": "ONLINE",
    "registration_starts_at": "2026-01-01T00:00:00Z",
    "registration_ends_at": "2027-01-01T00:00:00Z",
    "status": "REGISTRATION_OPEN",
    "pricing_plan_ids": [],
}
response, exam = runner.request(
    "REG-DIAG-001", "create_exam_api_v1_admin_exams_post", "Create diagnostic open exam",
    "POST", "/api/v1/admin/exams", kind="positive", expected={201}, headers=runner.admin_headers,
    body=exam_body,
)
if not response or response.status_code != 201:
    runner.finalize()
    raise SystemExit("Diagnostic exam creation failed")
exam_id = exam["id"]
runner.ledger["exams"].append({"id": exam_id, "slug": slug})
phone = "+98914" + f"{random.randint(1000000,9999999)}"
response, draft = runner.request(
    "REG-DIAG-002", "create_registration_api_v1_public_registrations_post", "Create diagnostic registration draft",
    "POST", "/api/v1/public/registrations", kind="positive", expected={201},
    body={"exam_offering_id": exam_id, "phone_number": phone},
)
if not response or response.status_code != 201:
    runner.finalize()
    raise SystemExit("Diagnostic registration creation failed")
registration_id = draft["registration"]["id"]
draft_headers = {"Authorization": f"Draft {draft['draft_token']}"}
runner.ledger["registrations"].append({"id": registration_id, "phone": phone})

fields = [
    ("first_name", "E2E"),
    ("last_name", "Diagnostic"),
    ("gender", "OTHER"),
    ("national_code", module.valid_national_code(module.RUN_ID + "diag")),
    ("father_name", "E2E Father"),
    ("birth_date", "2005-01-02"),
    ("home_phone", "02112345678"),
    ("postal_code", "1234567890"),
    ("address", "E2E diagnostic address"),
    ("extra_answers", {"run_id": module.RUN_ID}),
]
for index, (field, value) in enumerate(fields, 1):
    runner.request(
        f"REG-DIAG-PATCH-{index:02d}",
        "patch_registration_api_v1_public_registrations__registration_id__patch",
        f"Patch registration field {field} in isolation",
        "PATCH",
        f"/api/v1/public/registrations/{registration_id}",
        kind="positive",
        expected={200},
        headers=draft_headers,
        body={field: value},
    )

runner.request(
    "REG-DIAG-GET", "get_registration_api_v1_public_registrations__registration_id__get",
    "Read diagnostic registration after field-isolation patches", "GET",
    f"/api/v1/public/registrations/{registration_id}", kind="positive", expected={200}, headers=draft_headers,
)
response, _ = runner.request(
    "REG-DIAG-CANCEL", "update_registration_api_v1_admin_registrations__registration_id__patch",
    "Cancel diagnostic registration", "PATCH", f"/api/v1/admin/registrations/{registration_id}",
    kind="positive", expected={200}, headers=runner.admin_headers,
    body={"status": "CANCELLED", "internal_notes": f"{module.RUN_ID} diagnostic cleanup"},
)
if response and response.status_code == 200:
    runner.ledger["registrations"][-1]["cleanup_state"] = "CANCELLED"
response, _ = runner.request(
    "REG-DIAG-ARCHIVE", "archive_resource_api_v1_admin__resource___entity_id__delete",
    "Archive diagnostic exam", "DELETE", f"/api/v1/admin/exams/{exam_id}",
    kind="positive", expected={204}, headers=runner.admin_headers,
)
if response and response.status_code == 204:
    runner.ledger["exams"][-1]["cleanup_state"] = "ARCHIVED_OR_INACTIVE"
runner.finalize()
runner.client.close()
