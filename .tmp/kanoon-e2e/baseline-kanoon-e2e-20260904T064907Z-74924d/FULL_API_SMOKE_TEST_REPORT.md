# Kanoon Backend — Full API E2E Test Report

## Executive Summary

- Environment: deployed live test environment; resolved tenant `Chamestan`
- Base URL: `https://kanoon.esaminu.ir`
- OpenAPI source: supplied `openapi.json`; deployed `/openapi.json` canonically matched (SHA-256 `e8ca40eaf41c783c9fe151c3b2d43917cef11cfe434759c97704bb2aa98a2f08`)
- Run ID: `kanoon-e2e-20260904T064907Z-74924d`
- Started: 2026-09-04T06:49:07.499387+00:00
- Finished: 2026-09-04T07:07:43.615166+00:00
- Total OpenAPI operations: 84
- Operations exercised: 84
- Passed: 18
- Failed: 58
- Blocked: 8
- Not applicable: 0
- Overall result: **FAIL**

The deployment is not suitable for frontend integration, staging, or production. Core update paths and public media delivery are broken; OTP/payment completion and full cross-tenant proof remain blocked. The high failed-operation count also reflects systemic OpenAPI omissions, not 58 independent runtime outages.

## Critical Findings

- **P0:** none observed.
- **P1:** all nine generic admin content updates return 500; public registration PATCH returns 500 for every valid field; public media download URLs fail signature validation.
- **P2:** completion before object upload leaks an internal failure as HTTP 500.
- **P3:** unknown hosts receive an empty edge 200; 64 operations have observable OpenAPI response-contract gaps.

## Coverage Summary

| Area | Passed | Failed | Blocked | Notes |
|---|---:|---:|---:|---|
| Admin blog | 0 | 6 | 0 | Final result includes contract conformance |
| Admin content | 0 | 31 | 1 | Final result includes contract conformance |
| Admin media | 0 | 2 | 0 | Final result includes contract conformance |
| Admin registrations | 0 | 4 | 0 | Final result includes contract conformance |
| Authentication | 0 | 2 | 0 | Final result includes contract conformance |
| Health / pre-flight | 2 | 0 | 0 | Final result includes contract conformance |
| Internal build callback | 0 | 0 | 1 | Final result includes contract conformance |
| Payment | 1 | 0 | 1 | Final result includes contract conformance |
| Payment callback | 0 | 0 | 1 | Final result includes contract conformance |
| Public blog | 2 | 1 | 0 | Final result includes contract conformance |
| Public content | 10 | 4 | 1 | Final result includes contract conformance |
| Public media | 0 | 1 | 0 | Final result includes contract conformance |
| Registration / OTP / profile media | 3 | 4 | 3 | Final result includes contract conformance |
| Site build | 0 | 3 | 0 | Final result includes contract conformance |

## Endpoint Coverage

| Method | Path | Operation ID | Positive | Negative | Integration | Result |
|---|---|---|---|---|---|---|
| GET | /health/live | live_health_live_get | PASS | NOT_RUN | NOT_RUN | PASS |
| GET | /health/ready | ready_health_ready_get | PASS | NOT_RUN | NOT_RUN | PASS |
| POST | /api/v1/admin/auth/login | tenant_login_api_v1_admin_auth_login_post | PASS | FAIL | NOT_RUN | FAIL |
| POST | /api/v1/admin/auth/refresh | tenant_refresh_api_v1_admin_auth_refresh_post | PASS | FAIL | NOT_RUN | FAIL |
| POST | /api/v1/public/registrations | create_registration_api_v1_public_registrations_post | PASS | FAIL | NOT_RUN | FAIL |
| GET | /api/v1/public/registrations/{registration_id} | get_registration_api_v1_public_registrations__registration_id__get | PASS | FAIL | NOT_RUN | FAIL |
| PATCH | /api/v1/public/registrations/{registration_id} | patch_registration_api_v1_public_registrations__registration_id__patch | BLOCKED | FAIL | NOT_RUN | FAIL |
| POST | /api/v1/public/registrations/{registration_id}/token/rotate | rotate_draft_token_api_v1_public_registrations__registration_id__token_rotate_post | PASS | NOT_RUN | PASS | PASS |
| POST | /api/v1/public/registrations/{registration_id}/profile-image/upload | initiate_profile_image_upload_api_v1_public_registrations__registration_id__profile_image_upload_post | PASS | NOT_RUN | NOT_RUN | PASS |
| POST | /api/v1/public/registrations/{registration_id}/profile-image/{media_id}/complete | complete_profile_image_upload_api_v1_public_registrations__registration_id__profile_image__media_id__complete_post | PASS | FAIL | PASS | FAIL |
| PUT | /api/v1/public/registrations/{registration_id}/contacts | put_contacts_api_v1_public_registrations__registration_id__contacts_put | PASS | PASS | NOT_RUN | PASS |
| POST | /api/v1/public/registrations/{registration_id}/otp/send | send_otp_api_v1_public_registrations__registration_id__otp_send_post | BLOCKED | PASS | NOT_RUN | BLOCKED |
| POST | /api/v1/public/registrations/{registration_id}/otp/verify | verify_otp_api_v1_public_registrations__registration_id__otp_verify_post | BLOCKED | PASS | NOT_RUN | BLOCKED |
| POST | /api/v1/public/registrations/{registration_id}/submit | submit_registration_api_v1_public_registrations__registration_id__submit_post | BLOCKED | PASS | NOT_RUN | BLOCKED |
| POST | /api/v1/public/registrations/{registration_id}/payment | initiate_payment_api_v1_public_registrations__registration_id__payment_post | BLOCKED | PASS | NOT_RUN | BLOCKED |
| GET | /api/v1/public/registrations/{registration_id}/payment/status | payment_status_api_v1_public_registrations__registration_id__payment_status_get | PASS | NOT_RUN | NOT_RUN | PASS |
| GET | /api/v1/public/payments/callback/{provider_name} | payment_callback_api_v1_public_payments_callback__provider_name__get | BLOCKED | PASS | NOT_RUN | BLOCKED |
| POST | /api/v1/admin/media/uploads | initiate_upload_api_v1_admin_media_uploads_post | PASS | FAIL | NOT_RUN | FAIL |
| POST | /api/v1/admin/media/uploads/{media_id}/complete | complete_upload_api_v1_admin_media_uploads__media_id__complete_post | PASS | FAIL | NOT_RUN | FAIL |
| GET | /api/v1/public/media/{media_id} | download_media_api_v1_public_media__media_id__get | PASS | FAIL | FAIL | FAIL |
| GET | /api/v1/public/blog/snapshot | blog_snapshot_api_v1_public_blog_snapshot_get | PASS | NOT_RUN | NOT_RUN | PASS |
| GET | /api/v1/public/blog | list_blog_posts_api_v1_public_blog_get | PASS | PASS | NOT_RUN | PASS |
| GET | /api/v1/public/blog/{slug} | get_blog_post_api_v1_public_blog__slug__get | PASS | FAIL | PASS | FAIL |
| GET | /api/v1/public/site | site_bootstrap_api_v1_public_site_get | PASS | NOT_RUN | NOT_RUN | FAIL |
| GET | /api/v1/public/banners | banners_api_v1_public_banners_get | PASS | NOT_RUN | NOT_RUN | PASS |
| GET | /api/v1/public/news | news_api_v1_public_news_get | PASS | PASS | FAIL | FAIL |
| GET | /api/v1/public/news/{slug} | news_detail_api_v1_public_news__slug__get | BLOCKED | PASS | NOT_RUN | BLOCKED |
| GET | /api/v1/public/announcements | announcements_api_v1_public_announcements_get | PASS | PASS | PASS | PASS |
| GET | /api/v1/public/announcements/{slug} | announcement_detail_api_v1_public_announcements__slug__get | PASS | FAIL | PASS | FAIL |
| GET | /api/v1/public/honors | honors_api_v1_public_honors_get | PASS | PASS | PASS | PASS |
| GET | /api/v1/public/staff | staff_api_v1_public_staff_get | PASS | NOT_RUN | PASS | PASS |
| GET | /api/v1/public/pricing-plans | pricing_plans_api_v1_public_pricing_plans_get | PASS | NOT_RUN | PASS | PASS |
| GET | /api/v1/public/exams | exams_api_v1_public_exams_get | PASS | NOT_RUN | PASS | PASS |
| GET | /api/v1/public/school-directory | school_directory_api_v1_public_school_directory_get | PASS | PASS | NOT_RUN | PASS |
| GET | /api/v1/public/sample-exams | sample_exams_api_v1_public_sample_exams_get | PASS | PASS | NOT_RUN | PASS |
| GET | /api/v1/public/gallery | gallery_api_v1_public_gallery_get | PASS | PASS | PASS | PASS |
| GET | /api/v1/public/gallery/{slug} | gallery_detail_api_v1_public_gallery__slug__get | PASS | FAIL | PASS | FAIL |
| POST | /api/v1/public/contact-requests | create_contact_request_api_v1_public_contact_requests_post | PASS | PASS | NOT_RUN | PASS |
| GET | /api/v1/admin/blog | list_blog_posts_api_v1_admin_blog_get | PASS | FAIL | NOT_RUN | FAIL |
| POST | /api/v1/admin/blog | create_blog_post_api_v1_admin_blog_post | PASS | FAIL | NOT_RUN | FAIL |
| GET | /api/v1/admin/blog/{post_id} | get_blog_post_api_v1_admin_blog__post_id__get | PASS | FAIL | NOT_RUN | FAIL |
| PATCH | /api/v1/admin/blog/{post_id} | update_blog_post_api_v1_admin_blog__post_id__patch | PASS | FAIL | NOT_RUN | FAIL |
| POST | /api/v1/admin/blog/{post_id}/publish | publish_blog_post_api_v1_admin_blog__post_id__publish_post | PASS | FAIL | PASS | FAIL |
| POST | /api/v1/admin/blog/{post_id}/archive | archive_blog_post_api_v1_admin_blog__post_id__archive_post | PASS | FAIL | NOT_RUN | FAIL |
| GET | /api/v1/admin/posts | list_posts_api_v1_admin_posts_get | PASS | FAIL | NOT_RUN | FAIL |
| POST | /api/v1/admin/posts | create_post_api_v1_admin_posts_post | PASS | FAIL | NOT_RUN | FAIL |
| PUT | /api/v1/admin/posts/{entity_id} | update_post_api_v1_admin_posts__entity_id__put | NOT_RUN | FAIL | NOT_RUN | FAIL |
| GET | /api/v1/admin/banners | list_banners_api_v1_admin_banners_get | PASS | FAIL | NOT_RUN | FAIL |
| POST | /api/v1/admin/banners | create_banner_api_v1_admin_banners_post | PASS | FAIL | NOT_RUN | FAIL |
| GET | /api/v1/admin/honor-categories | list_honor_categories_api_v1_admin_honor_categories_get | PASS | FAIL | NOT_RUN | FAIL |
| POST | /api/v1/admin/honor-categories | create_honor_category_api_v1_admin_honor_categories_post | PASS | FAIL | NOT_RUN | FAIL |
| GET | /api/v1/admin/honors | list_honors_api_v1_admin_honors_get | PASS | FAIL | NOT_RUN | FAIL |
| POST | /api/v1/admin/honors | create_honor_api_v1_admin_honors_post | PASS | FAIL | NOT_RUN | FAIL |
| GET | /api/v1/admin/staff | list_staff_api_v1_admin_staff_get | PASS | FAIL | NOT_RUN | FAIL |
| POST | /api/v1/admin/staff | create_staff_api_v1_admin_staff_post | PASS | FAIL | NOT_RUN | FAIL |
| GET | /api/v1/admin/pricing-plans | list_pricing_api_v1_admin_pricing_plans_get | PASS | FAIL | NOT_RUN | FAIL |
| POST | /api/v1/admin/pricing-plans | create_pricing_api_v1_admin_pricing_plans_post | PASS | FAIL | NOT_RUN | FAIL |
| GET | /api/v1/admin/exams | list_exams_api_v1_admin_exams_get | PASS | FAIL | NOT_RUN | FAIL |
| POST | /api/v1/admin/exams | create_exam_api_v1_admin_exams_post | PASS | FAIL | NOT_RUN | FAIL |
| GET | /api/v1/admin/sample-exams | list_sample_exams_api_v1_admin_sample_exams_get | PASS | FAIL | NOT_RUN | FAIL |
| POST | /api/v1/admin/sample-exams | create_sample_exam_api_v1_admin_sample_exams_post | PASS | FAIL | NOT_RUN | FAIL |
| GET | /api/v1/admin/gallery | list_gallery_api_v1_admin_gallery_get | PASS | FAIL | NOT_RUN | FAIL |
| POST | /api/v1/admin/gallery | create_gallery_api_v1_admin_gallery_post | PASS | FAIL | NOT_RUN | FAIL |
| POST | /api/v1/admin/gallery/{album_id}/items | create_gallery_item_api_v1_admin_gallery__album_id__items_post | PASS | FAIL | NOT_RUN | FAIL |
| PUT | /api/v1/admin/school-profile | replace_school_profile_api_v1_admin_school_profile_put | BLOCKED | PASS | NOT_RUN | BLOCKED |
| GET | /api/v1/admin/contact-requests | list_contact_requests_api_v1_admin_contact_requests_get | PASS | FAIL | NOT_RUN | FAIL |
| PATCH | /api/v1/admin/contact-requests/{entity_id} | handle_contact_request_api_v1_admin_contact_requests__entity_id__patch | PASS | FAIL | PASS | FAIL |
| PUT | /api/v1/admin/banners/{entity_id} | update_banner_api_v1_admin_banners__entity_id__put | NOT_RUN | FAIL | NOT_RUN | FAIL |
| PUT | /api/v1/admin/honor-categories/{entity_id} | update_honor_category_api_v1_admin_honor_categories__entity_id__put | NOT_RUN | FAIL | NOT_RUN | FAIL |
| PUT | /api/v1/admin/honors/{entity_id} | update_honor_api_v1_admin_honors__entity_id__put | NOT_RUN | FAIL | NOT_RUN | FAIL |
| PUT | /api/v1/admin/staff/{entity_id} | update_staff_api_v1_admin_staff__entity_id__put | NOT_RUN | FAIL | NOT_RUN | FAIL |
| PUT | /api/v1/admin/pricing-plans/{entity_id} | update_pricing_plan_api_v1_admin_pricing_plans__entity_id__put | NOT_RUN | FAIL | NOT_RUN | FAIL |
| PUT | /api/v1/admin/exams/{entity_id} | update_exam_api_v1_admin_exams__entity_id__put | NOT_RUN | FAIL | NOT_RUN | FAIL |
| PUT | /api/v1/admin/sample-exams/{entity_id} | update_sample_exam_api_v1_admin_sample_exams__entity_id__put | NOT_RUN | FAIL | NOT_RUN | FAIL |
| PUT | /api/v1/admin/gallery/{entity_id} | update_gallery_album_api_v1_admin_gallery__entity_id__put | NOT_RUN | FAIL | NOT_RUN | FAIL |
| DELETE | /api/v1/admin/{resource}/{entity_id} | archive_resource_api_v1_admin__resource___entity_id__delete | PASS | FAIL | NOT_RUN | FAIL |
| GET | /api/v1/admin/site-build/status | build_status_api_v1_admin_site_build_status_get | PASS | FAIL | NOT_RUN | FAIL |
| GET | /api/v1/admin/site-build/history | build_history_api_v1_admin_site_build_history_get | PASS | FAIL | PASS | FAIL |
| POST | /api/v1/admin/site-build/rebuild | manual_rebuild_api_v1_admin_site_build_rebuild_post | PASS | FAIL | PASS | FAIL |
| GET | /api/v1/admin/registrations | list_registrations_api_v1_admin_registrations_get | PASS | FAIL | FAIL | FAIL |
| GET | /api/v1/admin/registrations/export.csv | export_registrations_api_v1_admin_registrations_export_csv_get | PASS | FAIL | PASS | FAIL |
| GET | /api/v1/admin/registrations/{registration_id} | registration_detail_api_v1_admin_registrations__registration_id__get | PASS | FAIL | FAIL | FAIL |
| PATCH | /api/v1/admin/registrations/{registration_id} | update_registration_api_v1_admin_registrations__registration_id__patch | PASS | FAIL | NOT_RUN | FAIL |
| POST | /api/v1/internal/site-builds/{request_id}/result | record_build_result_api_v1_internal_site_builds__request_id__result_post | BLOCKED | PASS | NOT_RUN | BLOCKED |

## End-to-End Workflow Results

### Pre-flight and Reliability

DNS resolved to `62.60.146.39`; TLS negotiated TLS 1.3 and the observed certificate expires 2026-11-06. Liveness and readiness returned JSON 200 in 74.32 ms and 50.61 ms. Deployed OpenAPI returned in 40.92 ms and canonically matched the supplied file. Across timed API checks, median was 50.61 ms, p95 74.32 ms, and maximum 928.30 ms (admin login). Three repeated health reads remained 200; no transient failure was hidden by retries.

### Authentication

Admin login succeeded with contract-shaped access/refresh tokens; the access token authorized protected resources. Missing, malformed, random, and refresh-token-as-bearer credentials were rejected. Refresh rotation produced a working access token; old-refresh reuse was rejected and revoked the rotated family. No credentials or complete tokens are retained.

### Registration

A draft was created from the run-owned exam/pricing pair, retrieved with draft authorization, given contacts and a real profile upload, rotated, and found via admin list/search/detail/CSV. The old draft token failed after rotation. Admin notes persisted. Cancellation succeeded and made the draft immutable. Public PATCH is broken for every tested field (FAIL-002).

### Media

Public PNG, public PDF, private PNG, and private profile PNG objects were uploaded through actual presigned storage POSTs and completed. Metadata matched deterministic fixtures where exposed. Private media returned 404 publicly. Public download redirection is unusable (FAIL-004), and premature completion returns 500 (FAIL-003).

### OTP

Malformed verification, missing challenge, invalid draft authorization, and bounded rejection behavior were exercised. No SMS was sent because no explicitly authorized test phone or OTP retrieval mechanism exists. Successful send/verification and replay testing are BLOCKED.

### Payment

Eligibility rejection, payment-status retrieval, missing/short idempotency-key validation, malformed registration access, unknown provider callback, and missing/tampered callback state were exercised. Legitimate initiation/idempotency replay/callback completion are BLOCKED behind OTP; no charge was attempted.

### Public/Admin Content

Run-owned announcement, banner, honor category/honor, staff, pricing plan, linked exam, sample exam, and gallery were created via admin and checked publicly. Archival/inactivation removed applicable public representations. Every generic PUT update returned 500 (FAIL-001); draft news therefore could not be published.

### Blog

Draft creation, admin list/detail, draft invisibility, update, publish, public list/detail/snapshot, duplicate/invalid slug rejection, archive, revision behavior, and public disappearance succeeded.

### Contact Requests

A unique public request was accepted, found in the admin list, transitioned to CLOSED with internal notes/handling metadata, and checked for validation and private-field behavior.

### Site Build

Status, history, and manual rebuild succeeded. The new request appeared in history and reached terminal `NOT_CONFIGURED`; successful external build completion is BLOCKED. Internal callbacks with missing, invalid, stale, or tampered signatures were rejected; a valid signed callback is BLOCKED because no authorized deployed signer is available.

### Tenant Isolation

The expected tenant resolved publicly and for admin. Admin routes rejected anonymous/random credentials; draft tokens could not access unrelated registrations; private media remained private; forwarded-host injection did not change scope. Full cross-tenant ID/RLS proof is BLOCKED because only one authorized tenant exists. Unknown-host routing is FAIL-005.

## Failed Tests

### FAIL-001 — All nine generic admin content update operations return HTTP 500

**Severity:** P1  
**Category:** BUSINESS_LOGIC  
**Endpoint(s):** PUT generic admin content update endpoints  
**Expected:** A valid update persists and is reflected by admin and public reads.  
**Actual:** Every generic update returned INTERNAL_SERVER_ERROR on fresh run-owned records. Draft news could not be published and remained absent publicly.  
**HTTP status:** 500  
**Reproduction:** Execute the cited test IDs using the runners under `.tmp/kanoon-e2e/`; credentials are entered interactively and are not stored.  
**Evidence:** ADMIN-CONTENT-002/005/007/009/011/013/015/017/020; PUBLIC-CONSISTENCY-NEWS  
**Probable root cause:** AdminContentService.update flushes a TimestampMixin entity and returns it without refreshing. SQLAlchemy expires server-updated updated_at; synchronous Pydantic serialization in the async request likely triggers MissingGreenlet. BlogService.update refreshes and succeeds.  
**Confidence:** high  
**Likely component:** `app/content/admin_service.py:102; app/core/models.py:29`  
**Recommended fix:** Refresh the updated entity after flush, or eagerly obtain server defaults, before response serialization.  
**Regression test:** For each generic family: create, PUT, admin-read, verify public projection where published, then archive.

### FAIL-002 — Public registration PATCH returns HTTP 500 for every valid field

**Severity:** P1  
**Category:** BUSINESS_LOGIC  
**Endpoint(s):** PATCH /api/v1/public/registrations/{registration_id}  
**Expected:** Valid draft-authorized fields persist and are returned.  
**Actual:** The combined update and ten isolated field updates all returned INTERNAL_SERVER_ERROR; follow-up GET confirmed no value persisted.  
**HTTP status:** 500  
**Reproduction:** Execute the cited test IDs using the runners under `.tmp/kanoon-e2e/`; credentials are entered interactively and are not stored.  
**Evidence:** REG-006; REG-DIAG-PATCH-01 through REG-DIAG-PATCH-10  
**Probable root cause:** RegistrationService.patch flushes an entity whose on-update timestamp becomes expired, then public serialization accesses updated_at without refresh.  
**Confidence:** high  
**Likely component:** `app/registrations/service.py:127; app/registrations/router.py:101`  
**Recommended fix:** Refresh the registration after flush before building the public response.  
**Regression test:** PATCH each field individually and combined; assert 200, persistence, unchanged unrelated fields, and valid updated_at.

### FAIL-003 — Completing a media upload before object upload returns HTTP 500

**Severity:** P2  
**Category:** ERROR_HANDLING  
**Endpoint(s):** Admin and registration-profile completion endpoints  
**Expected:** Missing object is rejected as a bounded 4xx state error.  
**Actual:** Both completion-before-upload cases returned INTERNAL_SERVER_ERROR; valid upload and completion succeeded.  
**HTTP status:** 500  
**Reproduction:** Execute the cited test IDs using the runners under `.tmp/kanoon-e2e/`; credentials are entered interactively and are not stored.  
**Evidence:** ADMIN-MEDIA-PREMATURE; MEDIA-PROFILE-002  
**Probable root cause:** The storage HEAD/inspect call raises provider NoSuchKey/ClientError that is not translated into an application error.  
**Confidence:** high  
**Likely component:** `app/media/router.py:96; app/registrations/router.py:224; storage adapter`  
**Recommended fix:** Catch missing-object provider errors and return a documented 409 or 422.  
**Regression test:** Complete before upload and assert documented 4xx, then upload and complete the same lifecycle.

### FAIL-004 — Public media redirects to an unusable signed object URL

**Severity:** P1  
**Category:** MEDIA_STORAGE  
**Endpoint(s):** GET /api/v1/public/media/{media_id}  
**Expected:** Redirect URL returns the uploaded bytes.  
**Actual:** API returned 307, but following the freshly generated storage URL returned SignatureDoesNotMatch. Storage POST and completion worked.  
**HTTP status:** 403  
**Reproduction:** Execute the cited test IDs using the runners under `.tmp/kanoon-e2e/`; credentials are entered interactively and are not stored.  
**Evidence:** MEDIA-PUBLIC-001; MEDIA-PUBLIC-002  
**Probable root cause:** The configured public S3 endpoint/proxy changes the host or path used by URL signing, so the gateway validates a different canonical request.  
**Confidence:** medium  
**Likely component:** `S3 public endpoint configuration and media presigning adapter`  
**Recommended fix:** Generate URLs against the externally reachable endpoint with the signature mode/canonical host accepted by the gateway.  
**Regression test:** Upload deterministic bytes, complete, follow untouched redirect, and compare SHA-256 and Content-Type.

### FAIL-005 — Unknown Host receives an empty HTTP 200 from the edge proxy

**Severity:** P3  
**Category:** TENANT_ISOLATION  
**Endpoint(s):** GET /api/v1/public/site with unauthorized Host  
**Expected:** Edge or tenant resolver rejects unknown host with non-2xx.  
**Actual:** Repeated requests returned an empty Caddy 200 with no tenant data or application headers, showing interception before FastAPI.  
**HTTP status:** 200  
**Reproduction:** Execute the cited test IDs using the runners under `.tmp/kanoon-e2e/`; credentials are entered interactively and are not stored.  
**Evidence:** TENANT-001 and controlled reproduction  
**Probable root cause:** The Caddy listener/default virtual host emits an empty success response for unmatched hosts.  
**Confidence:** high  
**Likely component:** `Caddy/default virtual-host configuration`  
**Recommended fix:** Add a default virtual host returning 404/421, or forward unknown hosts to tenant resolution.  
**Regression test:** Send TLS requests to the authorized address with unknown Host and require non-2xx/no tenant content.

### FAIL-006 — OpenAPI omits runtime errors and misdocuments CSV media type

**Severity:** P3  
**Category:** CONTRACT  
**Endpoint(s):** Authentication, admin, validation/not-found, callbacks, registration, media, and CSV  
**Expected:** Observable statuses, error bodies, and media types are represented in OpenAPI.  
**Actual:** 114 live undocumented-status observations plus one CSV mismatch affect 64 operations.  
**HTTP status:** multiple  
**Reproduction:** Execute the cited test IDs using the runners under `.tmp/kanoon-e2e/`; credentials are entered interactively and are not stored.  
**Evidence:** contract_violations in FULL_API_SMOKE_TEST_RESULTS.json  
**Probable root cause:** Routes omit reusable application-error response declarations; CSV export omits text/csv schema metadata.  
**Confidence:** high  
**Likely component:** `FastAPI route response declarations and admin CSV route`  
**Recommended fix:** Register ErrorBody responses and explicitly declare text/csv for export.  
**Regression test:** Generate OpenAPI in CI and compare all intentional runtime status/media-type combinations.

## Blocked Tests

Blocked external/safety-dependent flows prevent complete verification.

| Operation | Reason | Requirement to unblock |
|---|---|---|
| `send_otp_api_v1_public_registrations__registration_id__otp_send_post` | No explicitly authorized test phone or deployed OTP-test mechanism was supplied; no SMS was sent. | Explicitly authorized test phone and bounded SMS permission. |
| `verify_otp_api_v1_public_registrations__registration_id__otp_verify_post` | No authorized OTP retrieval/test-number mechanism is exposed by the deployed API. | Authorized OTP retrieval/test-code mechanism. |
| `submit_registration_api_v1_public_registrations__registration_id__submit_post` | Successful OTP verification is blocked. | Successful authorized OTP verification plus repaired registration PATCH. |
| `initiate_payment_api_v1_public_registrations__registration_id__payment_post` | Registration cannot become eligible without successful OTP verification; no OTP retrieval mechanism is authorized. | Eligible submitted registration and confirmed sandbox/zero-value gateway. |
| `payment_callback_api_v1_public_payments_callback__provider_name__get` | No eligible sandbox payment and signed callback state were available; no financial transaction was attempted. | Legitimate sandbox transaction and gateway-issued callback state. |
| `news_detail_api_v1_public_news__slug__get` | Public list contained no item that could be safely dereferenced. | Repair generic update so the isolated draft news can be published. |
| `replace_school_profile_api_v1_admin_school_profile_put` | Initial profile is null and the API has no lossless restore-to-null operation. | Lossless restore-to-null support or approved disposable tenant. |
| `record_build_result_api_v1_internal_site_builds__request_id__result_post` | No authorized deployed callback signing secret or generated callback payload was available. | Authorized deployed callback signer or genuine build callback. |

Additional boundary: complete cross-tenant RLS/ID isolation is BLOCKED because no second authorized tenant exists.

## Contract Violations

There are **115** violations affecting **64** operations: 114 live undocumented-status observations and one CSV media-type mismatch. Exact test/status evidence is in the JSON artifact.

| Operation ID | Violations | Summary |
|---|---:|---|
| `announcement_detail_api_v1_public_announcements__slug__get` | 3 | Undocumented status(es): 404 |
| `archive_blog_post_api_v1_admin_blog__post_id__archive_post` | 1 | Undocumented status(es): 401 |
| `archive_resource_api_v1_admin__resource___entity_id__delete` | 3 | Undocumented status(es): 401, 404 |
| `build_history_api_v1_admin_site_build_history_get` | 1 | Undocumented status(es): 401 |
| `build_status_api_v1_admin_site_build_status_get` | 1 | Undocumented status(es): 401 |
| `complete_profile_image_upload_api_v1_public_registrations__registration_id__profile_image__media_id__complete_post` | 1 | Undocumented status(es): 500 |
| `complete_upload_api_v1_admin_media_uploads__media_id__complete_post` | 2 | Undocumented status(es): 401, 500 |
| `create_banner_api_v1_admin_banners_post` | 1 | Undocumented status(es): 401 |
| `create_blog_post_api_v1_admin_blog_post` | 2 | Undocumented status(es): 401, 409 |
| `create_exam_api_v1_admin_exams_post` | 1 | Undocumented status(es): 401 |
| `create_gallery_api_v1_admin_gallery_post` | 1 | Undocumented status(es): 401 |
| `create_gallery_item_api_v1_admin_gallery__album_id__items_post` | 1 | Undocumented status(es): 401 |
| `create_honor_api_v1_admin_honors_post` | 1 | Undocumented status(es): 401 |
| `create_honor_category_api_v1_admin_honor_categories_post` | 1 | Undocumented status(es): 401 |
| `create_post_api_v1_admin_posts_post` | 1 | Undocumented status(es): 401 |
| `create_pricing_api_v1_admin_pricing_plans_post` | 1 | Undocumented status(es): 401 |
| `create_registration_api_v1_public_registrations_post` | 1 | Undocumented status(es): 404 |
| `create_sample_exam_api_v1_admin_sample_exams_post` | 1 | Undocumented status(es): 401 |
| `create_staff_api_v1_admin_staff_post` | 1 | Undocumented status(es): 401 |
| `download_media_api_v1_public_media__media_id__get` | 3 | Undocumented status(es): 404 |
| `export_registrations_api_v1_admin_registrations_export_csv_get` | 2 | Undocumented status(es): 200, 401; CSV declared application/json |
| `gallery_detail_api_v1_public_gallery__slug__get` | 2 | Undocumented status(es): 404 |
| `get_blog_post_api_v1_admin_blog__post_id__get` | 1 | Undocumented status(es): 401 |
| `get_blog_post_api_v1_public_blog__slug__get` | 3 | Undocumented status(es): 404 |
| `get_registration_api_v1_public_registrations__registration_id__get` | 3 | Undocumented status(es): 401, 404 |
| `handle_contact_request_api_v1_admin_contact_requests__entity_id__patch` | 1 | Undocumented status(es): 401 |
| `initiate_payment_api_v1_public_registrations__registration_id__payment_post` | 1 | Undocumented status(es): 400 |
| `initiate_upload_api_v1_admin_media_uploads_post` | 1 | Undocumented status(es): 401 |
| `list_banners_api_v1_admin_banners_get` | 4 | Undocumented status(es): 401 |
| `list_blog_posts_api_v1_admin_blog_get` | 1 | Undocumented status(es): 401 |
| `list_contact_requests_api_v1_admin_contact_requests_get` | 1 | Undocumented status(es): 401 |
| `list_exams_api_v1_admin_exams_get` | 1 | Undocumented status(es): 401 |
| `list_gallery_api_v1_admin_gallery_get` | 1 | Undocumented status(es): 401 |
| `list_honor_categories_api_v1_admin_honor_categories_get` | 1 | Undocumented status(es): 401 |
| `list_honors_api_v1_admin_honors_get` | 1 | Undocumented status(es): 401 |
| `list_posts_api_v1_admin_posts_get` | 1 | Undocumented status(es): 401 |
| `list_pricing_api_v1_admin_pricing_plans_get` | 1 | Undocumented status(es): 401 |
| `list_registrations_api_v1_admin_registrations_get` | 1 | Undocumented status(es): 401 |
| `list_sample_exams_api_v1_admin_sample_exams_get` | 1 | Undocumented status(es): 401 |
| `list_staff_api_v1_admin_staff_get` | 1 | Undocumented status(es): 401 |
| `manual_rebuild_api_v1_admin_site_build_rebuild_post` | 1 | Undocumented status(es): 401 |
| `news_detail_api_v1_public_news__slug__get` | 4 | Undocumented status(es): 404 |
| `patch_registration_api_v1_public_registrations__registration_id__patch` | 12 | Undocumented status(es): 400, 500 |
| `payment_callback_api_v1_public_payments_callback__provider_name__get` | 2 | Undocumented status(es): 401, 404 |
| `publish_blog_post_api_v1_admin_blog__post_id__publish_post` | 1 | Undocumented status(es): 401 |
| `record_build_result_api_v1_internal_site_builds__request_id__result_post` | 3 | Undocumented status(es): 401 |
| `registration_detail_api_v1_admin_registrations__registration_id__get` | 1 | Undocumented status(es): 401 |
| `replace_school_profile_api_v1_admin_school_profile_put` | 1 | Undocumented status(es): 401 |
| `send_otp_api_v1_public_registrations__registration_id__otp_send_post` | 1 | Undocumented status(es): 404 |
| `submit_registration_api_v1_public_registrations__registration_id__submit_post` | 1 | Undocumented status(es): 400 |
| `tenant_login_api_v1_admin_auth_login_post` | 1 | Undocumented status(es): 401 |
| `tenant_refresh_api_v1_admin_auth_refresh_post` | 5 | Undocumented status(es): 401 |
| `update_banner_api_v1_admin_banners__entity_id__put` | 3 | Undocumented status(es): 401, 500 |
| `update_blog_post_api_v1_admin_blog__post_id__patch` | 1 | Undocumented status(es): 401 |
| `update_exam_api_v1_admin_exams__entity_id__put` | 2 | Undocumented status(es): 401, 500 |
| `update_gallery_album_api_v1_admin_gallery__entity_id__put` | 2 | Undocumented status(es): 401, 500 |
| `update_honor_api_v1_admin_honors__entity_id__put` | 2 | Undocumented status(es): 401, 500 |
| `update_honor_category_api_v1_admin_honor_categories__entity_id__put` | 2 | Undocumented status(es): 401, 500 |
| `update_post_api_v1_admin_posts__entity_id__put` | 2 | Undocumented status(es): 401, 500 |
| `update_pricing_plan_api_v1_admin_pricing_plans__entity_id__put` | 2 | Undocumented status(es): 401, 500 |
| `update_registration_api_v1_admin_registrations__registration_id__patch` | 2 | Undocumented status(es): 400, 401 |
| `update_sample_exam_api_v1_admin_sample_exams__entity_id__put` | 3 | Undocumented status(es): 401, 500 |
| `update_staff_api_v1_admin_staff__entity_id__put` | 3 | Undocumented status(es): 401, 500 |
| `verify_otp_api_v1_public_registrations__registration_id__otp_verify_post` | 1 | Undocumented status(es): 400 |

## Security Findings

No P0 compromise was observed. Admin routes rejected anonymous and invalid credentials; token-type misuse and refresh replay were rejected; draft rotation revoked the old token; unrelated-registration token substitution failed; forged internal callbacks failed; private media stayed private; foreign-origin CORS preflight was rejected. Unknown-host edge 200 is a P3 defect. Cross-tenant proof remains blocked.

## Flaky/Intermittent Behavior

No transient failure was silently converted to PASS. Generic update, registration PATCH, public-media, premature-completion, and unknown-host failures reproduced consistently. No separate flaky defect was identified.

## Cleanup Results

Cleanup result: **PARTIAL**. All API-cleanable run-owned content was archived/inactivated; both test registrations are CANCELLED and the contact request is CLOSED. Four READY media objects remain because OpenAPI has no media delete/archive operation: two public fixtures and two private fixtures. No pre-existing resource was destructively changed.

## Final Coverage Reconciliation

The supplied `openapi.json` was reparsed after execution. Discovered operations: **84**. Operations in results: **84**. Missing operations: **none**. Every operation has exactly one final state.

## Final Verdict

**FAIL.** The environment remains useful for backend defect reproduction and limited continued development testing. It is **not suitable for frontend integration testing, staging, or production** until the P1 content-update, registration-update, and media-delivery defects are repaired and retested. Staging/production suitability additionally requires authorized OTP, sandbox payment/idempotency, successful site-build callback, and cross-tenant verification. Cleanup is partial because four API-undeletable test media objects remain.
