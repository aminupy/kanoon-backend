#!/usr/bin/env python3
"""Build final, redacted Kanoon live-E2E Markdown and JSON artifacts."""
from __future__ import annotations

import json, re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SPEC = json.loads((ROOT / "openapi.json").read_text())
DATA = json.loads((HERE / "results.raw.json").read_text())

def scrub(value: Any, key: str = "") -> Any:
    sensitive = {"authorization", "username", "email", "password", "access_token", "refresh_token",
                   "draft_token", "otp", "otp_code", "secret", "signature", "x-kanoon-signature"}
    if key.lower() in sensitive:
        return "<redacted>" if value not in (None, "") else value
    if isinstance(value, dict):
        return {k: scrub(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v, key) for v in value]
    if isinstance(value, str):
        if any(x in value for x in ("AWSAccessKeyId=", "X-Amz-Credential=", "X-Amz-Signature=")):
            p = urlsplit(value)
            return urlunsplit((p.scheme, p.netloc, p.path, "<redacted-presigned-query>", ""))
        return re.sub(r"(?i)Bearer\s+[A-Za-z0-9._~+\-/=]+", "Bearer <redacted>", value)
    return value

DATA = scrub(DATA)
OPS = {}
for path, item in SPEC["paths"].items():
    for method, op in item.items():
        if method in {"get", "post", "put", "patch", "delete"}:
            OPS[op["operationId"]] = {"method": method.upper(), "path": path,
                "tags": op.get("tags", []), "responses": set(op.get("responses", {}))}
assert len(OPS) == 84

# Retain the complete programmatic operation inventory used for reconciliation.
inventory = []
for path, item in SPEC["paths"].items():
    for method, op in item.items():
        if method not in {"get", "post", "put", "patch", "delete"}:
            continue
        parameters = list(item.get("parameters", [])) + list(op.get("parameters", []))
        by_location = {location: [p for p in parameters if p.get("in") == location]
                       for location in ("path", "query", "header")}
        request_schemas = {mime: body.get("schema") for mime, body in
                           op.get("requestBody", {}).get("content", {}).items()}
        response_schemas = {status: {mime: body.get("schema") for mime, body in response.get("content", {}).items()}
                            for status, response in op.get("responses", {}).items()}
        inventory.append({"method":method.upper(), "path":path, "operation_id":op["operationId"],
            "tags":op.get("tags", []), "security":op.get("security", SPEC.get("security", [])),
            "path_parameters":by_location["path"], "query_parameters":by_location["query"],
            "header_parameters":by_location["header"], "request_schema":request_schemas,
            "success_statuses":[s for s in op.get("responses", {}) if str(s).startswith("2")],
            "documented_error_statuses":[s for s in op.get("responses", {}) if not str(s).startswith("2")],
            "response_schema":response_schemas})
DATA["operation_inventory"] = inventory

UPDATE_OPS = {
    "update_post_api_v1_admin_posts__entity_id__put", "update_banner_api_v1_admin_banners__entity_id__put",
    "update_honor_category_api_v1_admin_honor_categories__entity_id__put", "update_honor_api_v1_admin_honors__entity_id__put",
    "update_staff_api_v1_admin_staff__entity_id__put", "update_pricing_plan_api_v1_admin_pricing_plans__entity_id__put",
    "update_exam_api_v1_admin_exams__entity_id__put", "update_sample_exam_api_v1_admin_sample_exams__entity_id__put",
    "update_gallery_album_api_v1_admin_gallery__entity_id__put"}
REG_PATCH = "patch_registration_api_v1_public_registrations__registration_id__patch"
COMPLETE_OPS = {"complete_upload_api_v1_admin_media_uploads__media_id__complete_post",
    "complete_profile_image_upload_api_v1_public_registrations__registration_id__profile_image__media_id__complete_post"}
MEDIA_GET = "download_media_api_v1_public_media__media_id__get"
SITE_GET = "site_bootstrap_api_v1_public_site_get"
NEWS_GET = "news_api_v1_public_news_get"
CSV_OP = "export_registrations_api_v1_admin_registrations_export_csv_get"

findings = [
 {"failure_id":"FAIL-001","title":"All nine generic admin content update operations return HTTP 500","severity":"P1","category":"BUSINESS_LOGIC",
  "operation_id":sorted(UPDATE_OPS),"endpoint":"PUT generic admin content update endpoints","expected":"A valid update persists and is reflected by admin and public reads.","actual_status":500,
  "actual":"Every generic update returned INTERNAL_SERVER_ERROR on fresh run-owned records. Draft news could not be published and remained absent publicly.",
  "evidence":["ADMIN-CONTENT-002/005/007/009/011/013/015/017/020","PUBLIC-CONSISTENCY-NEWS"],
  "probable_cause":"AdminContentService.update flushes a TimestampMixin entity and returns it without refreshing. SQLAlchemy expires server-updated updated_at; synchronous Pydantic serialization in the async request likely triggers MissingGreenlet. BlogService.update refreshes and succeeds.",
  "confidence":"high","likely_component":"app/content/admin_service.py:102; app/core/models.py:29",
  "recommended_fix":"Refresh the updated entity after flush, or eagerly obtain server defaults, before response serialization.",
  "regression_test":"For each generic family: create, PUT, admin-read, verify public projection where published, then archive."},
 {"failure_id":"FAIL-002","title":"Public registration PATCH returns HTTP 500 for every valid field","severity":"P1","category":"BUSINESS_LOGIC",
  "operation_id":REG_PATCH,"endpoint":"PATCH /api/v1/public/registrations/{registration_id}","expected":"Valid draft-authorized fields persist and are returned.","actual_status":500,
  "actual":"The combined update and ten isolated field updates all returned INTERNAL_SERVER_ERROR; follow-up GET confirmed no value persisted.",
  "evidence":["REG-006","REG-DIAG-PATCH-01 through REG-DIAG-PATCH-10"],
  "probable_cause":"RegistrationService.patch flushes an entity whose on-update timestamp becomes expired, then public serialization accesses updated_at without refresh.",
  "confidence":"high","likely_component":"app/registrations/service.py:127; app/registrations/router.py:101",
  "recommended_fix":"Refresh the registration after flush before building the public response.",
  "regression_test":"PATCH each field individually and combined; assert 200, persistence, unchanged unrelated fields, and valid updated_at."},
 {"failure_id":"FAIL-003","title":"Completing a media upload before object upload returns HTTP 500","severity":"P2","category":"ERROR_HANDLING",
  "operation_id":sorted(COMPLETE_OPS),"endpoint":"Admin and registration-profile completion endpoints","expected":"Missing object is rejected as a bounded 4xx state error.","actual_status":500,
  "actual":"Both completion-before-upload cases returned INTERNAL_SERVER_ERROR; valid upload and completion succeeded.",
  "evidence":["ADMIN-MEDIA-PREMATURE","MEDIA-PROFILE-002"],
  "probable_cause":"The storage HEAD/inspect call raises provider NoSuchKey/ClientError that is not translated into an application error.",
  "confidence":"high","likely_component":"app/media/router.py:96; app/registrations/router.py:224; storage adapter",
  "recommended_fix":"Catch missing-object provider errors and return a documented 409 or 422.",
  "regression_test":"Complete before upload and assert documented 4xx, then upload and complete the same lifecycle."},
 {"failure_id":"FAIL-004","title":"Public media redirects to an unusable signed object URL","severity":"P1","category":"MEDIA_STORAGE",
  "operation_id":MEDIA_GET,"endpoint":"GET /api/v1/public/media/{media_id}","expected":"Redirect URL returns the uploaded bytes.","actual_status":403,
  "actual":"API returned 307, but following the freshly generated storage URL returned SignatureDoesNotMatch. Storage POST and completion worked.",
  "evidence":["MEDIA-PUBLIC-001","MEDIA-PUBLIC-002"],
  "probable_cause":"The configured public S3 endpoint/proxy changes the host or path used by URL signing, so the gateway validates a different canonical request.",
  "confidence":"medium","likely_component":"S3 public endpoint configuration and media presigning adapter",
  "recommended_fix":"Generate URLs against the externally reachable endpoint with the signature mode/canonical host accepted by the gateway.",
  "regression_test":"Upload deterministic bytes, complete, follow untouched redirect, and compare SHA-256 and Content-Type."},
 {"failure_id":"FAIL-005","title":"Unknown Host receives an empty HTTP 200 from the edge proxy","severity":"P3","category":"TENANT_ISOLATION",
  "operation_id":SITE_GET,"endpoint":"GET /api/v1/public/site with unauthorized Host","expected":"Edge or tenant resolver rejects unknown host with non-2xx.","actual_status":200,
  "actual":"Repeated requests returned an empty Caddy 200 with no tenant data or application headers, showing interception before FastAPI.",
  "evidence":["TENANT-001 and controlled reproduction"],
  "probable_cause":"The Caddy listener/default virtual host emits an empty success response for unmatched hosts.",
  "confidence":"high","likely_component":"Caddy/default virtual-host configuration",
  "recommended_fix":"Add a default virtual host returning 404/421, or forward unknown hosts to tenant resolution.",
  "regression_test":"Send TLS requests to the authorized address with unknown Host and require non-2xx/no tenant content."}
]

# Contract conformance: expected negative responses still violate the contract when undocumented.
violations, contract_ops = [], set()
for test in DATA["tests"]:
    status, op_id = test.get("status_code"), test["operation_id"]
    if status is None or test.get("kind") == "integration":
        continue
    documented = OPS[op_id]["responses"]
    if str(status) not in documented:
        violations.append({"test_id":test["test_id"],"operation_id":op_id,"actual_status":status,
            "documented_statuses":sorted(documented),"detail":f"Observed HTTP {status}; absent from OpenAPI responses."})
        contract_ops.add(op_id)
violations.append({"test_id":"STATIC-CONTRACT-CSV-001","operation_id":CSV_OP,"actual_status":200,
    "documented_statuses":["200 application/json"],"detail":"Live response is text/csv; OpenAPI advertises application/json."})
contract_ops.add(CSV_OP)
findings.append({"failure_id":"FAIL-006","title":"OpenAPI omits runtime errors and misdocuments CSV media type","severity":"P3","category":"CONTRACT",
 "operation_id":f"multiple ({len(contract_ops)} operations)","endpoint":"Authentication, admin, validation/not-found, callbacks, registration, media, and CSV",
 "expected":"Observable statuses, error bodies, and media types are represented in OpenAPI.","actual_status":None,
 "actual":f"{len(violations)-1} live undocumented-status observations plus one CSV mismatch affect {len(contract_ops)} operations.",
 "evidence":["contract_violations in FULL_API_SMOKE_TEST_RESULTS.json"],
 "probable_cause":"Routes omit reusable application-error response declarations; CSV export omits text/csv schema metadata.",
 "confidence":"high","likely_component":"FastAPI route response declarations and admin CSV route",
 "recommended_fix":"Register ErrorBody responses and explicitly declare text/csv for export.",
 "regression_test":"Generate OpenAPI in CI and compare all intentional runtime status/media-type combinations."})

# Consolidate individual symptoms under root findings.
for test in DATA["tests"]:
    if test.get("result") != "FAIL":
        test["failure_id"] = None
        continue
    op_id = test["operation_id"]
    if op_id in UPDATE_OPS or op_id == NEWS_GET: test["failure_id"] = "FAIL-001"
    elif op_id == REG_PATCH: test["failure_id"] = "FAIL-002"
    elif op_id in COMPLETE_OPS: test["failure_id"] = "FAIL-003"
    elif op_id == MEDIA_GET: test["failure_id"] = "FAIL-004"
    elif op_id == SITE_GET: test["failure_id"] = "FAIL-005"
DATA["failures"], DATA["contract_violations"] = findings, violations

coverage = {row["operation_id"]: row for row in DATA["operation_coverage"]}
assert set(coverage) == set(OPS)
for op_id in contract_ops:
    row = coverage[op_id]
    if row["result"] != "BLOCKED":
        row.update(result="FAIL", negative="FAIL", reason="Runtime status and/or media type is undocumented in OpenAPI.")
for op_id in UPDATE_OPS | COMPLETE_OPS | {REG_PATCH, NEWS_GET, MEDIA_GET, SITE_GET}:
    coverage[op_id]["result"] = "FAIL"

# Machine-readable contract assertion for each affected operation.
known_ids = {t["test_id"] for t in DATA["tests"]}
for index, op_id in enumerate(sorted(contract_ops), 1):
    test_id = f"CONTRACT-{index:03d}"
    if test_id not in known_ids:
        DATA["tests"].append({"test_id":test_id,"timestamp":DATA.get("finished"),"operation_id":op_id,
            "scenario":"Actual response set and media types conform to supplied OpenAPI","kind":"contract","result":"FAIL",
            "timing_ms":0.0,"status_code":None,"method":OPS[op_id]["method"],"path":OPS[op_id]["path"],
            "failure_id":"FAIL-006","notes":"See contract_violations for exact observed evidence."})

tested = {t["operation_id"] for t in DATA["tests"]}
counts = Counter(row["result"] for row in DATA["operation_coverage"])
DATA.update(finished=datetime.now(timezone.utc).isoformat(), total_operations=len(OPS), operations_exercised=len(tested),
    passed=counts["PASS"], failed=counts["FAIL"], blocked=counts["BLOCKED"], not_applicable=counts["NOT_APPLICABLE"],
    overall_result="FAIL", missing_operations=sorted(set(OPS)-tested))
assert not DATA["missing_operations"] and DATA["operations_exercised"] == DATA["total_operations"] == 84
assert DATA["passed"] + DATA["failed"] + DATA["blocked"] + DATA["not_applicable"] == 84
assert (DATA["passed"],DATA["failed"],DATA["blocked"],DATA["not_applicable"]) == (18,58,8,0)
DATA = scrub(DATA)
payload = json.dumps(DATA, ensure_ascii=False, indent=2) + "\n"
(ROOT / "FULL_API_SMOKE_TEST_RESULTS.json").write_text(payload)
(HERE / "results.raw.json").write_text(payload)

def esc(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")

tag_names = {"health":"Health / pre-flight","admin-auth":"Authentication","public-registrations":"Registration / OTP / profile media",
 "public-payments":"Payment","payment-callbacks":"Payment callback","admin-media":"Admin media","public-media":"Public media",
 "public-blog":"Public blog","public-content":"Public content","admin-blog":"Admin blog","admin-content":"Admin content",
 "admin-site-build":"Site build","admin-registrations":"Admin registrations","internal-site-builds":"Internal build callback"}
areas = defaultdict(Counter)
for row in DATA["operation_coverage"]:
    tags = OPS[row["operation_id"]]["tags"]
    areas[tag_names.get(tags[0] if tags else "untagged", tags[0] if tags else "untagged")][row["result"]] += 1

lines = ["# Kanoon Backend — Full API E2E Test Report","","## Executive Summary","",
 "- Environment: deployed live test environment; resolved tenant `Chamestan`",f"- Base URL: `{DATA['base_url']}`",
 "- OpenAPI source: supplied `openapi.json`; deployed `/openapi.json` canonically matched (SHA-256 `e8ca40eaf41c783c9fe151c3b2d43917cef11cfe434759c97704bb2aa98a2f08`)",
 f"- Run ID: `{DATA['run_id']}`",f"- Started: {DATA['started']}",f"- Finished: {DATA['finished']}",
 f"- Total OpenAPI operations: {DATA['total_operations']}",f"- Operations exercised: {DATA['operations_exercised']}",
 f"- Passed: {DATA['passed']}",f"- Failed: {DATA['failed']}",f"- Blocked: {DATA['blocked']}",f"- Not applicable: {DATA['not_applicable']}",
 "- Overall result: **FAIL**","",
 "The deployment is not suitable for frontend integration, staging, or production. Core update paths and public media delivery are broken; OTP/payment completion and full cross-tenant proof remain blocked. The high failed-operation count also reflects systemic OpenAPI omissions, not 58 independent runtime outages.","",
 "## Critical Findings","","- **P0:** none observed.",
 "- **P1:** all nine generic admin content updates return 500; public registration PATCH returns 500 for every valid field; public media download URLs fail signature validation.",
 "- **P2:** completion before object upload leaks an internal failure as HTTP 500.",
 "- **P3:** unknown hosts receive an empty edge 200; 64 operations have observable OpenAPI response-contract gaps.","",
 "## Coverage Summary","","| Area | Passed | Failed | Blocked | Notes |","|---|---:|---:|---:|---|"]
for area in sorted(areas):
    c=areas[area]; lines.append(f"| {esc(area)} | {c['PASS']} | {c['FAIL']} | {c['BLOCKED']} | Final result includes contract conformance |")
lines += ["","## Endpoint Coverage","","| Method | Path | Operation ID | Positive | Negative | Integration | Result |","|---|---|---|---|---|---|---|"]
for row in DATA["operation_coverage"]:
    lines.append("| " + " | ".join(esc(row.get(k,"")) for k in ("method","path","operation_id","positive","negative","integration","result")) + " |")

lines += ["","## End-to-End Workflow Results","",
 "### Pre-flight and Reliability","",
 "DNS resolved to `62.60.146.39`; TLS negotiated TLS 1.3 and the observed certificate expires 2026-11-06. Liveness and readiness returned JSON 200 in 74.32 ms and 50.61 ms. Deployed OpenAPI returned in 40.92 ms and canonically matched the supplied file. Across timed API checks, median was 50.61 ms, p95 74.32 ms, and maximum 928.30 ms (admin login). Three repeated health reads remained 200; no transient failure was hidden by retries.","",
 "### Authentication","",
 "Admin login succeeded with contract-shaped access/refresh tokens; the access token authorized protected resources. Missing, malformed, random, and refresh-token-as-bearer credentials were rejected. Refresh rotation produced a working access token; old-refresh reuse was rejected and revoked the rotated family. No credentials or complete tokens are retained.","",
 "### Registration","",
 "A draft was created from the run-owned exam/pricing pair, retrieved with draft authorization, given contacts and a real profile upload, rotated, and found via admin list/search/detail/CSV. The old draft token failed after rotation. Admin notes persisted. Cancellation succeeded and made the draft immutable. Public PATCH is broken for every tested field (FAIL-002).","",
 "### Media","",
 "Public PNG, public PDF, private PNG, and private profile PNG objects were uploaded through actual presigned storage POSTs and completed. Metadata matched deterministic fixtures where exposed. Private media returned 404 publicly. Public download redirection is unusable (FAIL-004), and premature completion returns 500 (FAIL-003).","",
 "### OTP","",
 "Malformed verification, missing challenge, invalid draft authorization, and bounded rejection behavior were exercised. No SMS was sent because no explicitly authorized test phone or OTP retrieval mechanism exists. Successful send/verification and replay testing are BLOCKED.","",
 "### Payment","",
 "Eligibility rejection, payment-status retrieval, missing/short idempotency-key validation, malformed registration access, unknown provider callback, and missing/tampered callback state were exercised. Legitimate initiation/idempotency replay/callback completion are BLOCKED behind OTP; no charge was attempted.","",
 "### Public/Admin Content","",
 "Run-owned announcement, banner, honor category/honor, staff, pricing plan, linked exam, sample exam, and gallery were created via admin and checked publicly. Archival/inactivation removed applicable public representations. Every generic PUT update returned 500 (FAIL-001); draft news therefore could not be published.","",
 "### Blog","",
 "Draft creation, admin list/detail, draft invisibility, update, publish, public list/detail/snapshot, duplicate/invalid slug rejection, archive, revision behavior, and public disappearance succeeded.","",
 "### Contact Requests","",
 "A unique public request was accepted, found in the admin list, transitioned to CLOSED with internal notes/handling metadata, and checked for validation and private-field behavior.","",
 "### Site Build","",
 "Status, history, and manual rebuild succeeded. The new request appeared in history and reached terminal `NOT_CONFIGURED`; successful external build completion is BLOCKED. Internal callbacks with missing, invalid, stale, or tampered signatures were rejected; a valid signed callback is BLOCKED because no authorized deployed signer is available.","",
 "### Tenant Isolation","",
 "The expected tenant resolved publicly and for admin. Admin routes rejected anonymous/random credentials; draft tokens could not access unrelated registrations; private media remained private; forwarded-host injection did not change scope. Full cross-tenant ID/RLS proof is BLOCKED because only one authorized tenant exists. Unknown-host routing is FAIL-005.","",
 "## Failed Tests",""]
for f in findings:
    lines += [f"### {f['failure_id']} — {f['title']}","",f"**Severity:** {f['severity']}  ",f"**Category:** {f['category']}  ",
      f"**Endpoint(s):** {esc(f['endpoint'])}  ",f"**Expected:** {f['expected']}  ",f"**Actual:** {esc(f['actual'])}  ",
      f"**HTTP status:** {f['actual_status'] if f['actual_status'] is not None else 'multiple'}  ",
      "**Reproduction:** Execute the cited test IDs using the runners under `.tmp/kanoon-e2e/`; credentials are entered interactively and are not stored.  ",
      f"**Evidence:** {esc('; '.join(f['evidence']))}  ",f"**Probable root cause:** {f['probable_cause']}  ",
      f"**Confidence:** {f['confidence']}  ",f"**Likely component:** `{f['likely_component']}`  ",
      f"**Recommended fix:** {f['recommended_fix']}  ",f"**Regression test:** {f['regression_test']}",""]

blocked_rows=[r for r in DATA["operation_coverage"] if r["result"]=="BLOCKED"]
unblock={
 "send_otp_api_v1_public_registrations__registration_id__otp_send_post":"Explicitly authorized test phone and bounded SMS permission.",
 "verify_otp_api_v1_public_registrations__registration_id__otp_verify_post":"Authorized OTP retrieval/test-code mechanism.",
 "submit_registration_api_v1_public_registrations__registration_id__submit_post":"Successful authorized OTP verification plus repaired registration PATCH.",
 "initiate_payment_api_v1_public_registrations__registration_id__payment_post":"Eligible submitted registration and confirmed sandbox/zero-value gateway.",
 "payment_callback_api_v1_public_payments_callback__provider_name__get":"Legitimate sandbox transaction and gateway-issued callback state.",
 "news_detail_api_v1_public_news__slug__get":"Repair generic update so the isolated draft news can be published.",
 "replace_school_profile_api_v1_admin_school_profile_put":"Lossless restore-to-null support or approved disposable tenant.",
 "record_build_result_api_v1_internal_site_builds__request_id__result_post":"Authorized deployed callback signer or genuine build callback."}
lines += ["## Blocked Tests","","Blocked external/safety-dependent flows prevent complete verification.","",
 "| Operation | Reason | Requirement to unblock |","|---|---|---|"]
for r in blocked_rows:
    lines.append(f"| `{r['operation_id']}` | {esc(r.get('reason',''))} | {esc(unblock[r['operation_id']])} |")
lines += ["","Additional boundary: complete cross-tenant RLS/ID isolation is BLOCKED because no second authorized tenant exists.",""]

by_op=defaultdict(list)
for v in violations: by_op[v["operation_id"]].append(v)
lines += ["## Contract Violations","",f"There are **{len(violations)}** violations affecting **{len(contract_ops)}** operations: 114 live undocumented-status observations and one CSV media-type mismatch. Exact test/status evidence is in the JSON artifact.","",
 "| Operation ID | Violations | Summary |","|---|---:|---|"]
for op_id in sorted(by_op):
    rows=by_op[op_id]; statuses=sorted({str(v["actual_status"]) for v in rows if v["actual_status"] is not None})
    summary="Undocumented status(es): "+", ".join(statuses)
    if op_id==CSV_OP: summary += "; CSV declared application/json"
    lines.append(f"| `{op_id}` | {len(rows)} | {summary} |")

lines += ["","## Security Findings","",
 "No P0 compromise was observed. Admin routes rejected anonymous and invalid credentials; token-type misuse and refresh replay were rejected; draft rotation revoked the old token; unrelated-registration token substitution failed; forged internal callbacks failed; private media stayed private; foreign-origin CORS preflight was rejected. Unknown-host edge 200 is a P3 defect. Cross-tenant proof remains blocked.","",
 "## Flaky/Intermittent Behavior","",
 "No transient failure was silently converted to PASS. Generic update, registration PATCH, public-media, premature-completion, and unknown-host failures reproduced consistently. No separate flaky defect was identified.","",
 "## Cleanup Results","",
 "Cleanup result: **PARTIAL**. All API-cleanable run-owned content was archived/inactivated; both test registrations are CANCELLED and the contact request is CLOSED. Four READY media objects remain because OpenAPI has no media delete/archive operation: two public fixtures and two private fixtures. No pre-existing resource was destructively changed.","",
 "## Final Coverage Reconciliation","",
 "The supplied `openapi.json` was reparsed after execution. Discovered operations: **84**. Operations in results: **84**. Missing operations: **none**. Every operation has exactly one final state.","",
 "## Final Verdict","",
 "**FAIL.** The environment remains useful for backend defect reproduction and limited continued development testing. It is **not suitable for frontend integration testing, staging, or production** until the P1 content-update, registration-update, and media-delivery defects are repaired and retested. Staging/production suitability additionally requires authorized OTP, sandbox payment/idempotency, successful site-build callback, and cross-tenant verification. Cleanup is partial because four API-undeletable test media objects remain.",""]

(ROOT/"FULL_API_SMOKE_TEST_REPORT.md").write_text("\n".join(lines))
print(json.dumps({"report":str(ROOT/"FULL_API_SMOKE_TEST_REPORT.md"),"results":str(ROOT/"FULL_API_SMOKE_TEST_RESULTS.json"),
 "counts":{k:DATA[k] for k in ("passed","failed","blocked","not_applicable")},"operations":DATA["operations_exercised"],
 "tests":len(DATA["tests"]),"contract_violations":len(violations),"contract_operations":len(contract_ops)},indent=2))
