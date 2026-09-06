# Kanoon Backend — Full API E2E Test Report

## Executive Summary

- Run ID: `kanoon-fix-e2e-20260904T132520Z-a81eb8`
- Base URL: `https://kanoon.esaminu.ir`
- Deployed revision: `UNAVAILABLE` (no version endpoint/header)
- Overall result: **FAIL — NOT PRODUCTION-READY**
- Coverage matrix: 84/84 operations represented exactly once
- Live operations actually exercised after repair: 3/84
- PASS / FAIL / BLOCKED / NOT_APPLICABLE: 2 / 1 / 81 / 0

The corrected source and image passed local verification, but they could not be deployed: the repository contains no authorized production host, credential, or deployment workflow. The live edge and OpenAPI still exhibit baseline behavior, so stateful mutation testing was stopped before creating resources.

## Critical Findings

- P0: 0.
- P1: 3 remain open on the live deployment (FAIL-001, FAIL-002, FAIL-004).
- P2: 1 remains open on the live deployment (FAIL-003).
- P3: 2 remain open on the live deployment (FAIL-005, FAIL-006).
- All six have local fixes and regression evidence; none is live-closed without deployment.

## Coverage Summary

| Area | PASS | FAIL | BLOCKED |
|---|---:|---:|---:|
| admin-auth | 0 | 0 | 2 |
| admin-blog | 0 | 0 | 6 |
| admin-content | 0 | 0 | 32 |
| admin-media | 0 | 0 | 2 |
| admin-registrations | 0 | 0 | 4 |
| admin-site-build | 0 | 0 | 3 |
| health | 2 | 0 | 0 |
| internal-site-builds | 0 | 0 | 1 |
| payment-callbacks | 0 | 0 | 1 |
| public-blog | 0 | 0 | 3 |
| public-content | 0 | 1 | 14 |
| public-media | 0 | 0 | 1 |
| public-payments | 0 | 0 | 2 |
| public-registrations | 0 | 0 | 10 |

## Endpoint Coverage

| Method | Path | Operation ID | Positive | Negative | Integration | Result | Reason |
|---|---|---|---|---|---|---|---|
| POST | `/api/v1/admin/auth/login` | `tenant_login_api_v1_admin_auth_login_post` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| POST | `/api/v1/admin/auth/refresh` | `tenant_refresh_api_v1_admin_auth_refresh_post` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/admin/banners` | `list_banners_api_v1_admin_banners_get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| POST | `/api/v1/admin/banners` | `create_banner_api_v1_admin_banners_post` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| PUT | `/api/v1/admin/banners/{entity_id}` | `update_banner_api_v1_admin_banners__entity_id__put` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/admin/blog` | `list_blog_posts_api_v1_admin_blog_get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| POST | `/api/v1/admin/blog` | `create_blog_post_api_v1_admin_blog_post` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/admin/blog/{post_id}` | `get_blog_post_api_v1_admin_blog__post_id__get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| PATCH | `/api/v1/admin/blog/{post_id}` | `update_blog_post_api_v1_admin_blog__post_id__patch` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| POST | `/api/v1/admin/blog/{post_id}/archive` | `archive_blog_post_api_v1_admin_blog__post_id__archive_post` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| POST | `/api/v1/admin/blog/{post_id}/publish` | `publish_blog_post_api_v1_admin_blog__post_id__publish_post` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/admin/contact-requests` | `list_contact_requests_api_v1_admin_contact_requests_get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| PATCH | `/api/v1/admin/contact-requests/{entity_id}` | `handle_contact_request_api_v1_admin_contact_requests__entity_id__patch` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/admin/exams` | `list_exams_api_v1_admin_exams_get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| POST | `/api/v1/admin/exams` | `create_exam_api_v1_admin_exams_post` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| PUT | `/api/v1/admin/exams/{entity_id}` | `update_exam_api_v1_admin_exams__entity_id__put` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/admin/gallery` | `list_gallery_api_v1_admin_gallery_get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| POST | `/api/v1/admin/gallery` | `create_gallery_api_v1_admin_gallery_post` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| POST | `/api/v1/admin/gallery/{album_id}/items` | `create_gallery_item_api_v1_admin_gallery__album_id__items_post` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| PUT | `/api/v1/admin/gallery/{entity_id}` | `update_gallery_album_api_v1_admin_gallery__entity_id__put` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/admin/honor-categories` | `list_honor_categories_api_v1_admin_honor_categories_get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| POST | `/api/v1/admin/honor-categories` | `create_honor_category_api_v1_admin_honor_categories_post` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| PUT | `/api/v1/admin/honor-categories/{entity_id}` | `update_honor_category_api_v1_admin_honor_categories__entity_id__put` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/admin/honors` | `list_honors_api_v1_admin_honors_get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| POST | `/api/v1/admin/honors` | `create_honor_api_v1_admin_honors_post` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| PUT | `/api/v1/admin/honors/{entity_id}` | `update_honor_api_v1_admin_honors__entity_id__put` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| POST | `/api/v1/admin/media/uploads` | `initiate_upload_api_v1_admin_media_uploads_post` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| POST | `/api/v1/admin/media/uploads/{media_id}/complete` | `complete_upload_api_v1_admin_media_uploads__media_id__complete_post` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/admin/posts` | `list_posts_api_v1_admin_posts_get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| POST | `/api/v1/admin/posts` | `create_post_api_v1_admin_posts_post` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| PUT | `/api/v1/admin/posts/{entity_id}` | `update_post_api_v1_admin_posts__entity_id__put` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/admin/pricing-plans` | `list_pricing_api_v1_admin_pricing_plans_get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| POST | `/api/v1/admin/pricing-plans` | `create_pricing_api_v1_admin_pricing_plans_post` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| PUT | `/api/v1/admin/pricing-plans/{entity_id}` | `update_pricing_plan_api_v1_admin_pricing_plans__entity_id__put` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/admin/registrations` | `list_registrations_api_v1_admin_registrations_get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/admin/registrations/export.csv` | `export_registrations_api_v1_admin_registrations_export_csv_get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/admin/registrations/{registration_id}` | `registration_detail_api_v1_admin_registrations__registration_id__get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| PATCH | `/api/v1/admin/registrations/{registration_id}` | `update_registration_api_v1_admin_registrations__registration_id__patch` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/admin/sample-exams` | `list_sample_exams_api_v1_admin_sample_exams_get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| POST | `/api/v1/admin/sample-exams` | `create_sample_exam_api_v1_admin_sample_exams_post` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| PUT | `/api/v1/admin/sample-exams/{entity_id}` | `update_sample_exam_api_v1_admin_sample_exams__entity_id__put` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| PUT | `/api/v1/admin/school-profile` | `replace_school_profile_api_v1_admin_school_profile_put` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/admin/site-build/history` | `build_history_api_v1_admin_site_build_history_get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| POST | `/api/v1/admin/site-build/rebuild` | `manual_rebuild_api_v1_admin_site_build_rebuild_post` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/admin/site-build/status` | `build_status_api_v1_admin_site_build_status_get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/admin/staff` | `list_staff_api_v1_admin_staff_get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| POST | `/api/v1/admin/staff` | `create_staff_api_v1_admin_staff_post` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| PUT | `/api/v1/admin/staff/{entity_id}` | `update_staff_api_v1_admin_staff__entity_id__put` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| DELETE | `/api/v1/admin/{resource}/{entity_id}` | `archive_resource_api_v1_admin__resource___entity_id__delete` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| POST | `/api/v1/internal/site-builds/{request_id}/result` | `record_build_result_api_v1_internal_site_builds__request_id__result_post` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/public/announcements` | `announcements_api_v1_public_announcements_get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/public/announcements/{slug}` | `announcement_detail_api_v1_public_announcements__slug__get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/public/banners` | `banners_api_v1_public_banners_get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/public/blog` | `list_blog_posts_api_v1_public_blog_get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/public/blog/snapshot` | `blog_snapshot_api_v1_public_blog_snapshot_get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/public/blog/{slug}` | `get_blog_post_api_v1_public_blog__slug__get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| POST | `/api/v1/public/contact-requests` | `create_contact_request_api_v1_public_contact_requests_post` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/public/exams` | `exams_api_v1_public_exams_get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/public/gallery` | `gallery_api_v1_public_gallery_get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/public/gallery/{slug}` | `gallery_detail_api_v1_public_gallery__slug__get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/public/honors` | `honors_api_v1_public_honors_get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/public/media/{media_id}` | `download_media_api_v1_public_media__media_id__get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/public/news` | `news_api_v1_public_news_get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/public/news/{slug}` | `news_detail_api_v1_public_news__slug__get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/public/payments/callback/{provider_name}` | `payment_callback_api_v1_public_payments_callback__provider_name__get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/public/pricing-plans` | `pricing_plans_api_v1_public_pricing_plans_get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| POST | `/api/v1/public/registrations` | `create_registration_api_v1_public_registrations_post` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/public/registrations/{registration_id}` | `get_registration_api_v1_public_registrations__registration_id__get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| PATCH | `/api/v1/public/registrations/{registration_id}` | `patch_registration_api_v1_public_registrations__registration_id__patch` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| PUT | `/api/v1/public/registrations/{registration_id}/contacts` | `put_contacts_api_v1_public_registrations__registration_id__contacts_put` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| POST | `/api/v1/public/registrations/{registration_id}/otp/send` | `send_otp_api_v1_public_registrations__registration_id__otp_send_post` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| POST | `/api/v1/public/registrations/{registration_id}/otp/verify` | `verify_otp_api_v1_public_registrations__registration_id__otp_verify_post` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| POST | `/api/v1/public/registrations/{registration_id}/payment` | `initiate_payment_api_v1_public_registrations__registration_id__payment_post` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/public/registrations/{registration_id}/payment/status` | `payment_status_api_v1_public_registrations__registration_id__payment_status_get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| POST | `/api/v1/public/registrations/{registration_id}/profile-image/upload` | `initiate_profile_image_upload_api_v1_public_registrations__registration_id__profile_image_upload_post` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| POST | `/api/v1/public/registrations/{registration_id}/profile-image/{media_id}/complete` | `complete_profile_image_upload_api_v1_public_registrations__registration_id__profile_image__media_id__complete_post` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| POST | `/api/v1/public/registrations/{registration_id}/submit` | `submit_registration_api_v1_public_registrations__registration_id__submit_post` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| POST | `/api/v1/public/registrations/{registration_id}/token/rotate` | `rotate_draft_token_api_v1_public_registrations__registration_id__token_rotate_post` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/public/sample-exams` | `sample_exams_api_v1_public_sample_exams_get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/public/school-directory` | `school_directory_api_v1_public_school_directory_get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/api/v1/public/site` | `site_bootstrap_api_v1_public_site_get` | PASS | FAIL | NOT_RUN | FAIL | Canonical host remained usable, but unknown Host was not rejected. |
| GET | `/api/v1/public/staff` | `staff_api_v1_public_staff_get` | NOT_RUN | NOT_RUN | NOT_RUN | BLOCKED | Corrected backend was not deployed: the repository provides no authorized production host/credential/workflow, and the deployed OpenAPI/edge behavior prove the live service is still the baseline revision. |
| GET | `/health/live` | `live_health_live_get` | PASS | NOT_RUN | NOT_RUN | PASS | Fresh live health probe completed. |
| GET | `/health/ready` | `ready_health_ready_get` | PASS | NOT_RUN | NOT_RUN | PASS | Fresh live readiness probe completed. |

## End-to-End Workflow Results

| Workflow | Local result | Fresh live result |
|---|---|---|
| Nine generic content lifecycles | PASS for create/update/repeat/read/public/archive | BLOCKED: fixed build not deployed |
| Registration PATCH field matrix and token/state boundaries | PASS | BLOCKED: fixed build not deployed |
| Premature media completion, retry, and idempotency | PASS | BLOCKED: fixed build not deployed |
| Real S3 upload, public exact-byte download, private denial | PASS against disposable MinIO | BLOCKED: fixed build not deployed |
| Unknown-host rejection | PASS in middleware/config tests; Caddy config validates | FAIL: live edge returned empty 200 |
| OTP success/expiry/attempt/reuse | PASS with local gated mock provider | BLOCKED: no authorized live retrieval facility |
| Payment idempotency/callback/replay | PASS with local mock gateway | BLOCKED: no proven live sandbox/zero-value gateway |
| Site-build signed callback/replay | PASS locally | BLOCKED: no live signer/builder authority |
| Cross-tenant isolation | PASS with two local fixture tenants | BLOCKED: no second authorized live tenant |
| School profile replacement/restore | Existing local coverage only | BLOCKED: no disposable live tenant or restore-to-null API |

## Failed Tests

- `PREFLIGHT-UNKNOWN-HOST`: expected 404/421, received 200 from Caddy.
- Live OpenAPI drift remains: generated/supplied and deployed contracts are not canonically equal.

## Blocked Tests

- 81 operation IDs were not called against the known-old live deployment because those calls would not verify the repair and many require administrator credentials, which are unset.
- Deployment is blocked by missing repository-owned production target/credential/workflow.
- OTP, payment, site build, second-tenant, and school-profile prerequisites remain unavailable live.

## Contract Violations

- Local generated contract SHA-256: `c7261620d91a9ecc42b4d335c9e644a6960bbe5e33ceada277ecfd37207ec3bb`.
- Deployed contract SHA-256: `e8ca40eaf41c783c9fe151c3b2d43917cef11cfe434759c97704bb2aa98a2f08`.
- Operation response maps with drift: 83.
- Deployed reusable response components: 0.
- Deployed CSV success media type remains `application/json`; local generated contract is `text/csv`.

## Security Findings

- Unknown Host still receives HTTP 200 at the live edge; no tenant body leaked, but fail-closed routing is absent.
- An injected `X-Forwarded-Host` did not change canonical tenant selection in the bounded probe.
- No authentication token, OTP, signed URL query, signature, or credential was recorded.
- Local private-media denial and tenant isolation tests pass; live multi-tenant proof remains blocked.

## Flaky/Intermittent Behavior

No retries or transient failures occurred in the bounded fresh preflight. A complete post-deployment flakiness assessment is blocked.

## Cleanup Results

No live resources were created, so no live cleanup was necessary. The disposable local MinIO container and objects were removed after tests. Historical baseline artifacts/resources were not touched.

## Final Coverage Reconciliation

- 84/84 current OpenAPI operations appear exactly once in `operation_coverage`.
- Missing operation IDs: none.
- Actually exercised live operation IDs: 3/84.
- Final states: 2 PASS, 1 FAIL, 81 BLOCKED, 0 NOT_APPLICABLE.

## Final Verdict

**NOT PRODUCTION-READY.** The repaired build is locally green but is not deployed. Three P1 and one P2 defects therefore remain open on the live service, the live edge and OpenAPI still fail, and critical external workflows remain unverified.
