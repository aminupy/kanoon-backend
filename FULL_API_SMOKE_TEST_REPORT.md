# Kanoon Backend — Full API E2E Test Report

## Executive Summary

- Environment: deployed production tenant at `https://kanoon.esaminu.ir`
- Run ID: `kanoon-fix-e2e-20260906T105246Z-a3812b`
- Deployed revision: `0a9d06e6ca4e720025febb26ddc723484ea8d18b`
- GitHub deployment evidence: https://github.com/aminupy/kanoon-backend/actions/runs/34023040772
- Started: 2026-09-06T10:52:46.556430+00:00
- Finished: 2026-09-06T11:01:18.641126+00:00
- Operations represented: 84/84
- PASS / FAIL / BLOCKED / NOT_APPLICABLE: **76 / 1 / 7 / 0**
- Contract violations: **0**
- Overall verdict: **NOT PRODUCTION-READY**

Five original findings are verified fixed in production. Public media delivery remains broken, production is running mock OTP/payment providers, the deployed workflow bypasses its quality gates, and seven operations remain blocked by workflows that cannot be legitimately completed from the available test surface.

## Deployment and OpenAPI Verification

GitHub Actions recorded a successful production deployment of `0a9d06e6ca4e720025febb26ddc723484ea8d18b`. The deployed `/openapi.json` canonically matches the supplied contract at SHA-256 `c7261620d91a9ecc42b4d335c9e644a6960bbe5e33ceada277ecfd37207ec3bb`. The API does not expose a revision header, so revision attribution comes from the completed production deployment job.

The recorded GitHub run contained successful image-build and production-deploy jobs, but no quality job. In the deployed revision, the complete quality job and the image job's `needs: quality` dependency are commented out. Consequently, this deployment did not enforce pytest, Ruff, mypy, migration, or generated-OpenAPI gates.

## Coverage Summary

| Area | PASS | FAIL | BLOCKED | NOT_APPLICABLE |
|---|---:|---:|---:|---:|
| Admin blog | 6 | 0 | 0 | 0 |
| Admin content | 31 | 0 | 1 | 0 |
| Admin media | 2 | 0 | 0 | 0 |
| Admin registrations | 4 | 0 | 0 | 0 |
| Authentication | 2 | 0 | 0 | 0 |
| Health / pre-flight | 2 | 0 | 0 | 0 |
| Internal build callback | 0 | 0 | 1 | 0 |
| Payment | 1 | 0 | 1 | 0 |
| Payment callback | 0 | 0 | 1 | 0 |
| Public blog | 3 | 0 | 0 | 0 |
| Public content | 15 | 0 | 0 | 0 |
| Public media | 0 | 1 | 0 | 0 |
| Registration / OTP / profile media | 7 | 0 | 3 | 0 |
| Site build | 3 | 0 | 0 | 0 |

## Endpoint Coverage

| Method | Path | Operation ID | Positive | Negative | Integration | Result |
|---|---|---|---|---|---|---|
| POST | /api/v1/admin/auth/login | tenant_login_api_v1_admin_auth_login_post | PASS | PASS | NOT_RUN | PASS |
| POST | /api/v1/admin/auth/refresh | tenant_refresh_api_v1_admin_auth_refresh_post | PASS | PASS | NOT_RUN | PASS |
| GET | /api/v1/admin/banners | list_banners_api_v1_admin_banners_get | PASS | PASS | NOT_RUN | PASS |
| POST | /api/v1/admin/banners | create_banner_api_v1_admin_banners_post | PASS | PASS | NOT_RUN | PASS |
| PUT | /api/v1/admin/banners/{entity_id} | update_banner_api_v1_admin_banners__entity_id__put | PASS | PASS | NOT_RUN | PASS |
| GET | /api/v1/admin/blog | list_blog_posts_api_v1_admin_blog_get | PASS | PASS | NOT_RUN | PASS |
| POST | /api/v1/admin/blog | create_blog_post_api_v1_admin_blog_post | PASS | PASS | NOT_RUN | PASS |
| GET | /api/v1/admin/blog/{post_id} | get_blog_post_api_v1_admin_blog__post_id__get | PASS | PASS | NOT_RUN | PASS |
| PATCH | /api/v1/admin/blog/{post_id} | update_blog_post_api_v1_admin_blog__post_id__patch | PASS | PASS | NOT_RUN | PASS |
| POST | /api/v1/admin/blog/{post_id}/archive | archive_blog_post_api_v1_admin_blog__post_id__archive_post | PASS | PASS | NOT_RUN | PASS |
| POST | /api/v1/admin/blog/{post_id}/publish | publish_blog_post_api_v1_admin_blog__post_id__publish_post | PASS | PASS | PASS | PASS |
| GET | /api/v1/admin/contact-requests | list_contact_requests_api_v1_admin_contact_requests_get | PASS | PASS | NOT_RUN | PASS |
| PATCH | /api/v1/admin/contact-requests/{entity_id} | handle_contact_request_api_v1_admin_contact_requests__entity_id__patch | PASS | PASS | PASS | PASS |
| GET | /api/v1/admin/exams | list_exams_api_v1_admin_exams_get | PASS | PASS | NOT_RUN | PASS |
| POST | /api/v1/admin/exams | create_exam_api_v1_admin_exams_post | PASS | PASS | NOT_RUN | PASS |
| PUT | /api/v1/admin/exams/{entity_id} | update_exam_api_v1_admin_exams__entity_id__put | PASS | PASS | NOT_RUN | PASS |
| GET | /api/v1/admin/gallery | list_gallery_api_v1_admin_gallery_get | PASS | PASS | NOT_RUN | PASS |
| POST | /api/v1/admin/gallery | create_gallery_api_v1_admin_gallery_post | PASS | PASS | NOT_RUN | PASS |
| POST | /api/v1/admin/gallery/{album_id}/items | create_gallery_item_api_v1_admin_gallery__album_id__items_post | PASS | PASS | NOT_RUN | PASS |
| PUT | /api/v1/admin/gallery/{entity_id} | update_gallery_album_api_v1_admin_gallery__entity_id__put | PASS | PASS | NOT_RUN | PASS |
| GET | /api/v1/admin/honor-categories | list_honor_categories_api_v1_admin_honor_categories_get | PASS | PASS | NOT_RUN | PASS |
| POST | /api/v1/admin/honor-categories | create_honor_category_api_v1_admin_honor_categories_post | PASS | PASS | NOT_RUN | PASS |
| PUT | /api/v1/admin/honor-categories/{entity_id} | update_honor_category_api_v1_admin_honor_categories__entity_id__put | PASS | PASS | NOT_RUN | PASS |
| GET | /api/v1/admin/honors | list_honors_api_v1_admin_honors_get | PASS | PASS | NOT_RUN | PASS |
| POST | /api/v1/admin/honors | create_honor_api_v1_admin_honors_post | PASS | PASS | NOT_RUN | PASS |
| PUT | /api/v1/admin/honors/{entity_id} | update_honor_api_v1_admin_honors__entity_id__put | PASS | PASS | NOT_RUN | PASS |
| POST | /api/v1/admin/media/uploads | initiate_upload_api_v1_admin_media_uploads_post | PASS | PASS | NOT_RUN | PASS |
| POST | /api/v1/admin/media/uploads/{media_id}/complete | complete_upload_api_v1_admin_media_uploads__media_id__complete_post | PASS | PASS | NOT_RUN | PASS |
| GET | /api/v1/admin/posts | list_posts_api_v1_admin_posts_get | PASS | PASS | NOT_RUN | PASS |
| POST | /api/v1/admin/posts | create_post_api_v1_admin_posts_post | PASS | PASS | NOT_RUN | PASS |
| PUT | /api/v1/admin/posts/{entity_id} | update_post_api_v1_admin_posts__entity_id__put | PASS | PASS | NOT_RUN | PASS |
| GET | /api/v1/admin/pricing-plans | list_pricing_api_v1_admin_pricing_plans_get | PASS | PASS | NOT_RUN | PASS |
| POST | /api/v1/admin/pricing-plans | create_pricing_api_v1_admin_pricing_plans_post | PASS | PASS | NOT_RUN | PASS |
| PUT | /api/v1/admin/pricing-plans/{entity_id} | update_pricing_plan_api_v1_admin_pricing_plans__entity_id__put | PASS | PASS | NOT_RUN | PASS |
| GET | /api/v1/admin/registrations | list_registrations_api_v1_admin_registrations_get | PASS | PASS | PASS | PASS |
| GET | /api/v1/admin/registrations/export.csv | export_registrations_api_v1_admin_registrations_export_csv_get | PASS | PASS | PASS | PASS |
| GET | /api/v1/admin/registrations/{registration_id} | registration_detail_api_v1_admin_registrations__registration_id__get | PASS | PASS | PASS | PASS |
| PATCH | /api/v1/admin/registrations/{registration_id} | update_registration_api_v1_admin_registrations__registration_id__patch | PASS | PASS | NOT_RUN | PASS |
| GET | /api/v1/admin/sample-exams | list_sample_exams_api_v1_admin_sample_exams_get | PASS | PASS | NOT_RUN | PASS |
| POST | /api/v1/admin/sample-exams | create_sample_exam_api_v1_admin_sample_exams_post | PASS | PASS | NOT_RUN | PASS |
| PUT | /api/v1/admin/sample-exams/{entity_id} | update_sample_exam_api_v1_admin_sample_exams__entity_id__put | PASS | PASS | NOT_RUN | PASS |
| PUT | /api/v1/admin/school-profile | replace_school_profile_api_v1_admin_school_profile_put | BLOCKED | PASS | NOT_RUN | BLOCKED |
| GET | /api/v1/admin/site-build/history | build_history_api_v1_admin_site_build_history_get | PASS | PASS | PASS | PASS |
| POST | /api/v1/admin/site-build/rebuild | manual_rebuild_api_v1_admin_site_build_rebuild_post | PASS | PASS | PASS | PASS |
| GET | /api/v1/admin/site-build/status | build_status_api_v1_admin_site_build_status_get | PASS | PASS | NOT_RUN | PASS |
| GET | /api/v1/admin/staff | list_staff_api_v1_admin_staff_get | PASS | PASS | NOT_RUN | PASS |
| POST | /api/v1/admin/staff | create_staff_api_v1_admin_staff_post | PASS | PASS | NOT_RUN | PASS |
| PUT | /api/v1/admin/staff/{entity_id} | update_staff_api_v1_admin_staff__entity_id__put | PASS | PASS | NOT_RUN | PASS |
| DELETE | /api/v1/admin/{resource}/{entity_id} | archive_resource_api_v1_admin__resource___entity_id__delete | PASS | PASS | NOT_RUN | PASS |
| POST | /api/v1/internal/site-builds/{request_id}/result | record_build_result_api_v1_internal_site_builds__request_id__result_post | BLOCKED | PASS | NOT_RUN | BLOCKED |
| GET | /api/v1/public/announcements | announcements_api_v1_public_announcements_get | PASS | PASS | PASS | PASS |
| GET | /api/v1/public/announcements/{slug} | announcement_detail_api_v1_public_announcements__slug__get | PASS | PASS | PASS | PASS |
| GET | /api/v1/public/banners | banners_api_v1_public_banners_get | PASS | NOT_RUN | NOT_RUN | PASS |
| GET | /api/v1/public/blog | list_blog_posts_api_v1_public_blog_get | PASS | PASS | NOT_RUN | PASS |
| GET | /api/v1/public/blog/snapshot | blog_snapshot_api_v1_public_blog_snapshot_get | PASS | NOT_RUN | NOT_RUN | PASS |
| GET | /api/v1/public/blog/{slug} | get_blog_post_api_v1_public_blog__slug__get | PASS | PASS | PASS | PASS |
| POST | /api/v1/public/contact-requests | create_contact_request_api_v1_public_contact_requests_post | PASS | PASS | NOT_RUN | PASS |
| GET | /api/v1/public/exams | exams_api_v1_public_exams_get | PASS | NOT_RUN | PASS | PASS |
| GET | /api/v1/public/gallery | gallery_api_v1_public_gallery_get | PASS | PASS | PASS | PASS |
| GET | /api/v1/public/gallery/{slug} | gallery_detail_api_v1_public_gallery__slug__get | PASS | PASS | PASS | PASS |
| GET | /api/v1/public/honors | honors_api_v1_public_honors_get | PASS | PASS | PASS | PASS |
| GET | /api/v1/public/media/{media_id} | download_media_api_v1_public_media__media_id__get | PASS | PASS | FAIL | FAIL |
| GET | /api/v1/public/news | news_api_v1_public_news_get | PASS | PASS | PASS | PASS |
| GET | /api/v1/public/news/{slug} | news_detail_api_v1_public_news__slug__get | PASS | PASS | PASS | PASS |
| GET | /api/v1/public/payments/callback/{provider_name} | payment_callback_api_v1_public_payments_callback__provider_name__get | BLOCKED | PASS | NOT_RUN | BLOCKED |
| GET | /api/v1/public/pricing-plans | pricing_plans_api_v1_public_pricing_plans_get | PASS | NOT_RUN | PASS | PASS |
| POST | /api/v1/public/registrations | create_registration_api_v1_public_registrations_post | PASS | NOT_RUN | NOT_RUN | PASS |
| GET | /api/v1/public/registrations/{registration_id} | get_registration_api_v1_public_registrations__registration_id__get | PASS | PASS | NOT_RUN | PASS |
| PATCH | /api/v1/public/registrations/{registration_id} | patch_registration_api_v1_public_registrations__registration_id__patch | PASS | PASS | NOT_RUN | PASS |
| PUT | /api/v1/public/registrations/{registration_id}/contacts | put_contacts_api_v1_public_registrations__registration_id__contacts_put | PASS | PASS | NOT_RUN | PASS |
| POST | /api/v1/public/registrations/{registration_id}/otp/send | send_otp_api_v1_public_registrations__registration_id__otp_send_post | BLOCKED | PASS | NOT_RUN | BLOCKED |
| POST | /api/v1/public/registrations/{registration_id}/otp/verify | verify_otp_api_v1_public_registrations__registration_id__otp_verify_post | BLOCKED | PASS | NOT_RUN | BLOCKED |
| POST | /api/v1/public/registrations/{registration_id}/payment | initiate_payment_api_v1_public_registrations__registration_id__payment_post | BLOCKED | PASS | NOT_RUN | BLOCKED |
| GET | /api/v1/public/registrations/{registration_id}/payment/status | payment_status_api_v1_public_registrations__registration_id__payment_status_get | PASS | NOT_RUN | NOT_RUN | PASS |
| POST | /api/v1/public/registrations/{registration_id}/profile-image/upload | initiate_profile_image_upload_api_v1_public_registrations__registration_id__profile_image_upload_post | PASS | NOT_RUN | NOT_RUN | PASS |
| POST | /api/v1/public/registrations/{registration_id}/profile-image/{media_id}/complete | complete_profile_image_upload_api_v1_public_registrations__registration_id__profile_image__media_id__complete_post | PASS | PASS | PASS | PASS |
| POST | /api/v1/public/registrations/{registration_id}/submit | submit_registration_api_v1_public_registrations__registration_id__submit_post | BLOCKED | PASS | NOT_RUN | BLOCKED |
| POST | /api/v1/public/registrations/{registration_id}/token/rotate | rotate_draft_token_api_v1_public_registrations__registration_id__token_rotate_post | PASS | NOT_RUN | PASS | PASS |
| GET | /api/v1/public/sample-exams | sample_exams_api_v1_public_sample_exams_get | PASS | PASS | NOT_RUN | PASS |
| GET | /api/v1/public/school-directory | school_directory_api_v1_public_school_directory_get | PASS | PASS | NOT_RUN | PASS |
| GET | /api/v1/public/site | site_bootstrap_api_v1_public_site_get | PASS | PASS | NOT_RUN | PASS |
| GET | /api/v1/public/staff | staff_api_v1_public_staff_get | PASS | NOT_RUN | PASS | PASS |
| GET | /health/live | live_health_live_get | PASS | NOT_RUN | NOT_RUN | PASS |
| GET | /health/ready | ready_health_ready_get | PASS | NOT_RUN | NOT_RUN | PASS |

## Integrated Workflow Results

### Authentication and authorization

Administrator login, access-token authorization, refresh rotation, old-refresh replay rejection, token-family revocation, anonymous denial, malformed credentials, and token-type misuse passed. Complete credentials and tokens are not retained.

### Generic content and blog

All nine generic create → update → admin read → public visibility → archive lifecycles passed. Every formerly failing PUT returned HTTP 200. Blog draft/update/publish/public/archive behavior passed, including duplicate and malformed slug rejection.

### Registration

Draft creation, representative PATCH persistence, contacts, draft-token rotation, admin list/detail/notes/CSV, cancellation, and post-cancellation immutability passed. Successful OTP, submission, and legitimate payment remain blocked.

### Media

Actual presigned uploads and completion passed for public PNG, public PDF, private PNG, and private profile image. Premature completion returned structured HTTP 409 for both admin and profile endpoints. Private objects remained unavailable publicly. The public redirect still failed when its untouched signed URL returned storage HTTP 403 `SignatureDoesNotMatch`.

### Site build

Manual rebuild/history/status requests passed, but the observed terminal sequence was `['NOT_CONFIGURED']`. It ended `NOT_CONFIGURED`; no authorized valid HMAC callback was available.

### Tenant and edge behavior

The canonical domain resolved the bootstrapped tenant. An unknown Host returned Caddy HTTP 421 with an empty non-sensitive body, and injected `X-Forwarded-Host` did not change tenant selection. Full bidirectional isolation remains blocked because no second authorized tenant/domain exists.

## Fixed Baseline Findings

- Generic admin content updates: **FIXED** — all nine updates and lifecycles passed.
- Registration PATCH: **FIXED** — response and subsequent reads persisted updates.
- Premature media completion: **FIXED** — both endpoints returned documented 409.
- Unknown Host empty 200: **FIXED** — edge returned non-cacheable 421.
- OpenAPI response contract: **FIXED** — supplied/deployed documents match and this run found zero application-contract violations.
- Public media download URL: **NOT FIXED** — redirected storage request returned 403.

## Remaining Findings

### FAIL-001 — Public media redirect still produces an unusable signed URL

- Severity: **P1**
- Category: `MEDIA_STORAGE`
- Endpoint/component: GET /api/v1/public/media/dc3944a9-2988-495a-a6a7-2e013160c8b5
- Expected: 307 followed by successful object retrieval (HTTP 200)
- Actual: {'storage_error_code': 'SignatureDoesNotMatch', 'message': 'The request signature we calculated does not match the signature you provided. Check your key and signing method.', 'bytes': 574}
- Recommended fix: Align KANOON_S3_PUBLIC_ENDPOINT_URL with the browser-visible gateway and configure that proxy to preserve Host, path, and query exactly as signed.

### FAIL-002 — Deployed production revision permits and uses mock OTP/payment providers

- Severity: **P1**
- Category: `SECURITY_CONFIGURATION`
- Endpoint/component: Production application composition
- Expected: Production rejects mock providers and wires approved external adapters.
- Actual: The deployed revision comments out the production settings guard. The live payment callback identifies the active gateway as mock; the repository contains no concrete external OTP/payment adapter in the default application factory.
- Recommended fix: Deploy concrete production OTP/payment adapters and restore the settings guard; never deploy mock providers in production.

### FAIL-003 — Production deployment bypasses repository quality gates

- Severity: **P1**
- Category: `DELIVERY_PIPELINE`
- Endpoint/component: .github/workflows/ci.yml
- Expected: Every production candidate passes formatting, lint, typing, tests, migrations, and OpenAPI verification before image build and deployment.
- Actual: The entire quality job is commented out and the container job's dependency on quality is also commented out. GitHub Actions run 34023040772 therefore executed only the image-build and production-deploy jobs.
- Recommended fix: Restore the quality job and make the image-build job depend on it; require the quality check in branch protection before the next production deployment.

## Blocked Tests

| Operation | Reason |
|---|---|
| `replace_school_profile_api_v1_admin_school_profile_put` | Initial profile is null and the API has no lossless restore-to-null operation. |
| `record_build_result_api_v1_internal_site_builds__request_id__result_post` | No authorized deployed callback signing secret or generated callback payload was available. |
| `payment_callback_api_v1_public_payments_callback__provider_name__get` | No eligible sandbox payment and signed callback state were available; no financial transaction was attempted. |
| `send_otp_api_v1_public_registrations__registration_id__otp_send_post` | No explicitly authorized test phone or deployed OTP-test mechanism was supplied; no SMS was sent. |
| `verify_otp_api_v1_public_registrations__registration_id__otp_verify_post` | No authorized OTP retrieval/test-number mechanism is exposed by the deployed API. |
| `initiate_payment_api_v1_public_registrations__registration_id__payment_post` | Registration cannot become eligible without successful OTP verification; no OTP retrieval mechanism is authorized. |
| `submit_registration_api_v1_public_registrations__registration_id__submit_post` | Successful OTP verification is blocked. |

Additional environment-level blocker: full cross-tenant isolation cannot be proven without a second explicitly authorized tenant/domain.

## Contract Violations

**0.** The edge-only 421 is not a FastAPI response and is correctly excluded from the application OpenAPI contract.

## Security Review

Authentication, refresh replay protection, draft-token rotation, private-media denial, invalid callback signatures, tenant Host handling, and anonymous authorization checks passed. Production mock OTP/payment providers and bypassed CI quality gates remain P1 defects. No secret, complete token, OTP, signature, or presigned query is retained in the artifacts.

## Timing and Flakiness

Recorded request timing: median 75.22 ms, p95 130.17 ms, maximum 905.95 ms. Repeated health checks returned `[200, 200, 200]`. No transient failure was silently retried into PASS.

## Cleanup

Cleanup result: **PARTIAL**. All API-cleanable content was archived/inactivated; media has no delete operation and contact requests are retained as CLOSED. API-undeletable artifacts: 4.

## Final Reconciliation

OpenAPI operations: **84**. Coverage rows: **84**. Missing operations: **0**. Every operation has exactly one final state.

## Final Verdict

**NOT PRODUCTION-READY.** Public media delivery remains a P1 defect; production uses mock OTP/payment providers; the deployment pipeline bypasses its mandatory quality gates; OTP/payment/site-build success and a valid internal callback are unverified; and authorized two-tenant isolation proof is unavailable.
