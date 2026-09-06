# Kanoon Backend — Fix Implementation Report

## Verdict

**NOT PRODUCTION-READY.** All six reported defects have source/configuration fixes and local
regression evidence, but no corrected revision was deployed. A production CI/CD workflow and
host-side release procedure are now implemented, but the GitHub production environment, SSH/GHCR
credentials, and host-owned runtime configuration have not been supplied or exercised.
Administrator credentials are also unset. Fresh live preflight proves the service still runs the
baseline contract and edge behavior.

## Baseline Summary

- Baseline run: `kanoon-e2e-20260904T064907Z-74924d`
- Baseline result: FAIL
- Coverage: 84/84 operations
- Classification: 18 PASS, 58 FAIL, 8 BLOCKED, 0 NOT_APPLICABLE
- Consolidated findings: 3 P1, 1 P2, 2 P3
- Contract evidence: 115 violations affecting 64 operations
- Historical artifacts were copied byte-for-byte to
  `.tmp/kanoon-e2e/baseline-kanoon-e2e-20260904T064907Z-74924d/` before the canonical smoke
  artifacts were replaced.

## Files and Components Changed

- Content update/archive lifecycle: `app/content/admin_service.py`,
  `app/content/admin_router.py`, and `app/content/models.py`.
- Registration update validation/session lifecycle: `app/registrations/service.py` and
  `app/registrations/router.py`.
- Storage error translation and completion: `app/media/storage.py` and `app/media/router.py`.
- Public S3 signing separation already present in the current repository revision was retained and
  reverified through `app/core/config.py` and `app/media/storage.py`.
- Schema migration: `migrations/versions/c6e4a12b7f90_content_archive_markers.py`.
- OpenAPI customization/export: `app/core/openapi.py`, `app/main.py`, `app/control_plane.py`,
  `app/cli.py`, `Makefile`, and regenerated `openapi.json`.
- Edge routing example and deployment guidance: `deploy/Caddyfile.example` and
  `docs/deployment.md`.
- Production runtime topology and PostgreSQL 18 role provisioning:
  `docker-compose.production.yml`, `deploy/postgres/init/00-kanoon-roles.sh`, and the protected
  environment templates under `deploy/production/`.
- Production delivery: `.github/workflows/ci.yml`, `deploy/production/deploy.sh`,
  `deploy/production/verify_openapi.py`, and `docs/github-cicd.md`. The pipeline tests every push,
  builds every candidate image, publishes successful `main` images to GHCR by immutable digest,
  serializes production deploys, gates services on migrations, verifies readiness/OpenAPI, and
  performs application-only rollback while retaining forward database migrations.
- Regression coverage: `tests/integration/test_admin_content_update_api.py`,
  `tests/integration/test_media_completion_api.py`,
  `tests/integration/test_registration_patch_api.py`,
  `tests/integration/test_s3_storage_adapter.py`,
  `tests/integration/test_update_serialization.py`, `tests/unit/test_media_completion.py`,
  `tests/unit/test_openapi_contract.py`, `tests/unit/test_production_compose_contract.py`,
  `tests/unit/test_cicd_contract.py`, `tests/unit/test_production_release_scripts.py`, and
  extensions to domain/deployment/storage tests.

## Proven Root Causes and Repairs

### FAIL-001 — Generic admin content updates

`TimestampMixin.updated_at` is produced by a SQL-side on-update expression. After `flush()`,
SQLAlchemy expires the attribute; response-model serialization then accessed it outside explicit
async I/O and raised `MissingGreenlet`. Red regression tests demonstrated the expired attribute for
all nine generic families. `AdminContentService.update` now refreshes the entity before returning.
The update remains within the existing transaction and row-lock boundary.

The same work also closed ordinary-client error paths discovered by the new lifecycle suite:
integrity conflicts are translated to structured 409 responses, exam pricing-plan associations are
read back from persisted join rows, archived generic resources cannot be reactivated by PUT, and
honor-category/staff archive markers now give those families lossless public-disappearance
semantics.

### FAIL-002 — Registration PATCH

`RegistrationService.patch` had the same expired SQL-side timestamp lifecycle and serialized the
registration without refresh. It now refreshes after flush. Related school and profile-media IDs
are checked explicitly, tenant-scoped where applicable, and rejected as structured 422 errors
before database constraint failures can escape. Existing row locking, phone-change OTP
invalidation, and transaction rollback behavior are preserved.

### FAIL-003 — Premature media completion

The S3-compatible HEAD call surfaced provider `NoSuchKey`/404 errors through the storage adapter.
Both completion routers assumed a stored-object value and converted the missing-object state into
an unhandled 500. The adapter now maps only recognized missing-object responses to `None`; other
provider failures still propagate for observability. Both APIs translate `None` to structured 409
`MEDIA_OBJECT_NOT_UPLOADED`, leave media PENDING, permit a later successful upload/completion, and
retain the intended idempotent READY response.

### FAIL-004 — Public media download URL

The pre-repair design signed browser URLs with the backend-internal S3 endpoint. A public proxy
changing that canonical host/path produces the observed `SignatureDoesNotMatch`. The current source
uses separate internal-operation and browser-presigning clients, requires an HTTPS public S3
endpoint in production, and documents host/path/query preservation. A real MinIO integration test
performed presigned upload, completion, untouched redirect following, exact byte/SHA comparison,
Content-Type validation, and private-object denial. The fix is not considered live-closed because
production endpoint/proxy configuration could not be deployed or inspected.

### FAIL-005 — Unknown hosts

Fresh and baseline responses were empty HTTP 200 responses with `Server: Caddy` and no application
headers, proving the unmatched request terminates at the edge. The repository now contains a
canonical-host proxy block and a catch-all TLS listener that emits non-cacheable HTTP 421. It strips
client-supplied `X-Forwarded-Host` before proxying. Application tenant resolution continues to trust
forwarded host only from configured CIDRs. The Caddy configuration validates locally, but the live
edge still returns 200.

### FAIL-006 — OpenAPI response contract

FastAPI generated validation responses but the application did not attach its structured runtime
authentication, authorization, not-found, conflict, size, rate-limit, readiness, or business-rule
errors. CSV export also lacked explicit response content metadata. The installed OpenAPI extension
defines reusable `ErrorBody` responses for 400, 401, 403, 404, 409, 413, 422, 429, and 503 and maps
only reachable statuses to each operation. CSV is declared solely as `text/csv`, binary string, with
`Content-Disposition`. A canonical CLI target regenerates `openapi.json`, and contract tests assert
the intentional response/status/media mappings.

## Regression Tests Added

- Nine generic families: create, PUT, repeated PUT, admin list persistence, relationship retention,
  public projection when active/published, archive, and public disappearance.
- Generic malformed/nonexistent UUIDs, invalid enums/bounds/relations, duplicate slugs, gallery
  media errors, and mutation after archive.
- All 14 supported registration PATCH fields individually and in combination, fresh GET
  persistence, unchanged fields, monotonic timestamps, token absence/malformed/random/cross-draft/
  rotation boundaries, immutable states, validation boundaries, and invalid related IDs.
- Both media completion endpoints: missing object to 409, retryability, later success, mismatch, and
  repeated completion.
- Actual S3-compatible presigned upload/download and public/private API behavior.
- Reusable error responses, route-specific response maps, CSV content declaration, unknown-host
  edge policy, forwarded-host trust, and deployment configuration invariants.

Existing integration coverage also exercises two-tenant RLS/isolation, OTP expiry/attempt limits/
one-time consumption/resend cooldown, payment idempotency/callback/replay, and signed site-build
callbacks. These are local results only and do not substitute for the required live workflows.

## Local Quality Gates

| Gate | Result |
|---|---|
| Full pytest suite with real PostgreSQL 18 and disposable MinIO | PASS — 115 tests in 21.39s |
| Focused red/green serialization tests | PASS — all 10 repaired after failing on expired `updated_at` |
| Ruff format and lint (`app tests migrations deploy/production`) | PASS — 113 files formatted; all checks passed |
| Strict mypy (`app tests deploy/production/verify_openapi.py`) | PASS — 109 source files |
| Alembic downgrade to `8f3a2d6b9c10`, upgrade to head, and autogenerate check | PASS |
| Current migration head | `c6e4a12b7f90` |
| Dependency lock and installed-package compatibility | PASS |
| Caddy parse/validation using `caddy:2.10-alpine` | PASS |
| Production Compose render and shell syntax | PASS |
| Disposable `postgres:18-alpine` initialization/role audit | PASS — PostgreSQL 18.6, correct PGDATA and restricted roles |
| Production Docker image build | PASS — image `90db1bc473c90f297e6d4c67135847a54d7cce3efd7f5bb07be89d21f62e0dcc` |
| GitHub workflow lint (`actionlint` 1.7.7) | PASS |
| Production shell lint (`shellcheck`) | PASS |
| Generated/committed OpenAPI canonical comparison | PASS |
| Configured static/security checks | PASS via Ruff's selected security rules; no separate scanner is configured |

## Migration and Deployment

The new migration adds nullable `archived_at` columns to `honor_categories` and `staff_members` and
has a matching downgrade. Local upgrade/downgrade and schema-drift checks pass.

No live migration or application deployment was performed. The repository now contains a complete
GitHub Actions/SSH release workflow and exact production-environment setup documentation, but its
required GitHub variables/secrets and host-owned environment files are external state and have not
been configured in this session. Guessing a server credential or pushing `main` is not authorized.
The default production application factory also has no concrete external OTP/payment adapters, so
it deliberately fails closed until those integrations are implemented. `ADMIN_USERNAME` and
`ADMIN_PASSWORD` are unset, so stateful authenticated live verification cannot proceed.

- Local repository HEAD: `6906e25065338227249f3000ba5b1f31550b7758` plus the uncommitted repair worktree.
- Built repair image: `90db1bc473c90f297e6d4c67135847a54d7cce3efd7f5bb07be89d21f62e0dcc`.
- Deployed revision: unavailable; the service exposes no revision header/body/endpoint.
- Deployment result: **BLOCKED — workflow is implemented but production credentials/configuration
  and required external adapters are unavailable**.

## Before/After Evidence

| Finding | Baseline live | Local repaired result | Fresh live result |
|---|---|---|---|
| FAIL-001 | Nine valid updates returned 500 | All nine lifecycle tests pass | BLOCKED; repair not deployed |
| FAIL-002 | Combined and isolated PATCH returned 500/no persistence | Field matrix and fresh reads pass | BLOCKED; repair not deployed |
| FAIL-003 | Both premature completions returned 500 | Structured 409, retry, success, idempotency pass | BLOCKED; repair not deployed |
| FAIL-004 | 307 target returned 403 signature mismatch | Exact-byte real-S3 download and private denial pass | BLOCKED; repair/config not deployed |
| FAIL-005 | Empty Caddy 200 | Caddy 421 policy and trust tests pass | FAIL; empty Caddy 200 reproduced |
| FAIL-006 | 115 violations; CSV JSON declaration | Reusable errors and CSV contract tests pass | FAIL; old deployed schema reproduced |

## OpenAPI Drift

- Generated/supplied canonical SHA-256: `c7261620d91a9ecc42b4d335c9e644a6960bbe5e33ceada277ecfd37207ec3bb`.
- Deployed canonical SHA-256: `e8ca40eaf41c783c9fe151c3b2d43917cef11cfe434759c97704bb2aa98a2f08`.
- Both contain 84 operation IDs, but 83 operation response maps differ.
- Generated contract contains nine reusable structured error responses; deployed contains zero.
- Generated CSV content is `text/csv`; deployed content remains `application/json`.
- Result: **FAIL — supplied/generated/deployed contracts do not agree**.

## Residual Risks and Blockers

- The corrected application, migration, Caddy policy, and S3 public-endpoint configuration are not
  deployed; consequently all live P1/P2 findings remain open. The delivery workflow exists but its
  GitHub production environment and host prerequisites are not configured here.
- Concrete production OTP and payment adapters are absent. The application correctly refuses to
  use mocks in production, so automatic deployment will fail closed until these adapters exist.
- No administrator credentials were provided for a fresh authenticated run.
- No authorized second live tenant/domain exists for bidirectional isolation proof.
- No safe live OTP retrieval/test-number facility is exposed.
- No proven sandbox or zero-value live payment gateway is available; no money was spent.
- No authorized site-builder HMAC secret or live builder facility is available.
- School profile cannot be losslessly restored to null and no disposable live tenant is approved.
- Production S3 proxy/signing compatibility remains a deployment-time integration risk despite the
  passing real-S3 local test.

## Rollback Plan

No live rollback is presently required because no live state changed. The new deployment script
retains exact image digests and `current`/`previous` release links, and automatically restores the
previous application containers when rollout/readiness/OpenAPI verification fails. Database
migrations are intentionally forward-only. For an authorized deployment:

1. Retain the currently deployed application image and rendered Caddy configuration before release.
2. Apply `alembic upgrade c6e4a12b7f90` through the normal migration process, deploy the matching
   application image, validate health/OpenAPI, then atomically reload the validated Caddy config.
3. On application failure, restore the prior application and Caddy config. Downgrade the schema to
   `8f3a2d6b9c10` only after the prior application is active and only if the two nullable archive
   columns must be removed.
4. Preserve S3 credentials and bucket privacy. Restore endpoint configuration only together with a
   compatible application revision; never expose the internal endpoint publicly.
5. Re-run bounded readiness and the full fresh live suite before accepting either release or
   rollback.

## Production-Readiness Decision

**NOT PRODUCTION-READY.** Local implementation quality gates pass, but the required deployment and
fresh stateful 84-operation verification did not occur. The live service retains 3 P1, 1 P2, and 2
P3 findings, OpenAPI drift, and unverified critical external workflows.
