# Kanoon Backend — Fix Implementation Report

## Verdict

**NOT PRODUCTION-READY.** Revision `0a9d06e6ca4e720025febb26ddc723484ea8d18b` was deployed by the
repository CI/CD workflow and exercised in a fresh authenticated 84-operation run. Five of the six
baseline findings are verified fixed. Public media download still fails with an untouched signed
URL, production is running mock OTP/payment providers after the deployed revision disabled the
fail-closed configuration guard, the successful deployment bypassed the commented-out quality job,
and seven operations remain blocked by unavailable safe external workflows. The current worktree
repairs SigV4 media signing, CI/release gating, and lossless school-profile reset and expands the
local contract to 85 operations, but those changes are not deployed yet.

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
  `deploy/production/verify_openapi.py`, and `docs/github-cicd.md`. The deployment script gates
  services on migrations, verifies readiness/OpenAPI, and supports application-only rollback while
  retaining forward database migrations. However, the deployed workflow has its entire quality job
  and the image job's `needs: quality` dependency commented out; this is a live delivery defect,
  not an accepted implementation state. The current worktree restores both gates, verifies the
  image revision label, readiness, deployed OpenAPI, and atomic release links.
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

The live redirect inspection proved that boto3 was generating legacy Signature V2 query
authentication (`AWSAccessKeyId`, `Expires`, and `Signature`). The download also signs an encoded
`response-content-disposition` override. SeaweedFS 4.37 canonicalizes that received V2 query
differently, so it calculates a different signature even though the identity, bucket permission,
bucket name, and object key are correct. Presigned POST works because it signs a policy document
rather than the failing GET canonical resource.

`S3ObjectStorage` now gives both the internal-operation and browser-presigning clients an explicit
botocore configuration using Signature V4 and path-style bucket addressing. Regression assertions
reject legacy V2 fields and require `AWS4-HMAC-SHA256` plus a host-signed path-style URL. A
disposable PostgreSQL 18 and MinIO integration run performed presigned upload, inspection,
untouched public redirect following, exact byte comparison, Content-Type validation, private-object
denial, and cleanup. This fix remains pending production deployment and a fresh live exact-byte
verification.

### FAIL-005 — Unknown hosts

Fresh and baseline responses were empty HTTP 200 responses with `Server: Caddy` and no application
headers, proving the unmatched request terminates at the edge. The repository now contains a
canonical-host proxy block and a catch-all TLS listener that emits non-cacheable HTTP 421. It strips
client-supplied `X-Forwarded-Host` before proxying. Application tenant resolution continues to trust
forwarded host only from configured CIDRs. The fresh live run confirmed the edge now returns an
empty, non-cacheable HTTP 421 and forwarded-host injection cannot change tenant selection.

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
- Explicit SigV4/path-style presign assertions that reject legacy Signature V2 query fields.
- Reusable error responses, route-specific response maps, CSV content declaration, unknown-host
  edge policy, forwarded-host trust, and deployment configuration invariants.
- School-profile replace → public projection → idempotent reset → original null projection.

Existing integration coverage also exercises two-tenant RLS/isolation, OTP expiry/attempt limits/
one-time consumption/resend cooldown, payment idempotency/callback/replay, and signed site-build
callbacks. These are local results only and do not substitute for the required live workflows.

## Local Quality Gates

| Gate | Result |
|---|---|
| Current full pytest suite with real PostgreSQL 18 and disposable MinIO | PASS — 116 tests in 15.82s |
| Focused red/green serialization tests | PASS — all 10 repaired after failing on expired `updated_at` |
| Ruff format and lint (`app tests migrations deploy/production`) | PASS — 113 files formatted; all checks passed |
| Strict mypy (`app tests deploy/production/verify_openapi.py`) | PASS — 109 source files |
| Alembic downgrade to `8f3a2d6b9c10`, upgrade to head, and autogenerate check | PASS |
| Current migration head | `c6e4a12b7f90` |
| Dependency lock and installed-package compatibility | PASS |
| Caddy parse/validation using `caddy:2.10-alpine` | PASS |
| Production Compose render and shell syntax | PASS |
| Disposable `postgres:18-alpine` initialization/role audit | PASS — PostgreSQL 18.6, correct PGDATA and restricted roles |
| Production Docker image build and OCI revision-label verification | PASS |
| GitHub workflow lint (`actionlint` 1.7.7) | PASS |
| Production shell lint (`shellcheck`) | PASS |
| Generated/committed OpenAPI canonical comparison | PASS |
| Focused media suite with disposable PostgreSQL 18 and MinIO | PASS — 14 tests |
| SigV4 media unit tests | PASS — 9 tests |
| Real SigV4 storage/public-route tests with disposable PostgreSQL 18 and MinIO | PASS — 2 tests |
| Configured static/security checks | PASS via Ruff's selected security rules; no separate scanner is configured |

## Migration and Deployment

The new migration adds nullable `archived_at` columns to `honor_categories` and `staff_members` and
has a matching downgrade. Local upgrade/downgrade and schema-drift checks pass.

GitHub Actions run `34023040772` completed its production deployment job successfully, including
the migration-gated deployment step. Live readiness returned 200 and the deployed contract matches
the supplied contract. The API exposes no revision header; deployed revision attribution is based
on the successful production job and its recorded head SHA. The run contained only build and deploy
jobs: `.github/workflows/ci.yml` has the quality job and the container job's quality dependency
commented out, so that run did not execute pytest, Ruff, mypy, migration, or OpenAPI quality gates.
The current worktree restores those gates and passes their local equivalents; a new GitHub run is
still required.

- Local repository base HEAD: `0a9d06e6ca4e720025febb26ddc723484ea8d18b`; the current uncommitted
  repair set includes restoration of the production mock-provider guard.
- Deployed revision: `0a9d06e6ca4e720025febb26ddc723484ea8d18b`.
- Deployment evidence: `https://github.com/aminupy/kanoon-backend/actions/runs/34023040772`.
- Deployment result: **TECHNICALLY SUCCESSFUL, QUALITY-GATE FAIL** — image build, migration-gated
  rollout, readiness, and OpenAPI checks passed, but pre-deployment quality enforcement was absent.
- Fresh live run: `kanoon-fix-e2e-20260906T105246Z-a3812b` — 76 PASS, 1 FAIL, 7 BLOCKED,
  0 NOT_APPLICABLE.

## Before/After Evidence

| Finding | Baseline live | Local repaired result | Fresh live result |
|---|---|---|---|
| FAIL-001 | Nine valid updates returned 500 | All nine lifecycle tests pass | PASS; all nine live PUTs returned 200 and lifecycles completed |
| FAIL-002 | Combined and isolated PATCH returned 500/no persistence | Field matrix and fresh reads pass | PASS; PATCH returned 200 and subsequent reads persisted values |
| FAIL-003 | Both premature completions returned 500 | Structured 409, retry, success, idempotency pass | PASS; both live premature completions returned documented 409 |
| FAIL-004 | 307 target returned 403 signature mismatch | Exact-byte real-S3 download and private denial pass | FAIL; untouched live redirect still ends in storage 403 `SignatureDoesNotMatch` |
| FAIL-005 | Empty Caddy 200 | Caddy 421 policy and trust tests pass | PASS; unmatched Host returned empty non-cacheable edge 421 |
| FAIL-006 | 115 violations; CSV JSON declaration | Reusable errors and CSV contract tests pass | PASS; supplied and deployed contracts agree with zero run violations |

## OpenAPI Drift

- Current generated/supplied canonical SHA-256:
  `fd45f938549593dd5dfa4aee2ae6d53311a910395fc7a2da96d95e7d30993f61`.
- Current generated contract contains 85 operation IDs, including idempotent school-profile reset.
- Deployed revision still exposes the prior 84-operation contract at SHA-256
  `c7261620d91a9ecc42b4d335c9e644a6960bbe5e33ceada277ecfd37207ec3bb`.
- Registration CSV is declared and returned as `text/csv`.
- Fresh live contract violations: zero. The edge-only 421 is outside the FastAPI contract.
- Result: **EXPECTED PRE-DEPLOYMENT DRIFT — deploy and reverify the 85-operation contract**.

## Residual Risks and Blockers

- Public media download remains broken in production: API redirect succeeds, but the untouched
  storage request returns HTTP 403 `SignatureDoesNotMatch`. The SigV4/path-style correction is
  locally verified but has not yet been deployed.
- Concrete production OTP and payment adapters are absent. The deployed revision comments out the
  production guard, and live provider-name behavior confirms the mock payment gateway is active.
  The guard is restored in the worktree, so deployment now fails closed until real adapters are
  selected and wired.
- CI quality, revision, readiness, OpenAPI, and atomic release-link gates are repaired locally but
  need one successful GitHub build/deployment run before the delivery finding is closed.
- No authorized second live tenant/domain exists for bidirectional isolation proof.
- No safe live OTP retrieval/test-number facility is exposed.
- No proven sandbox or zero-value live payment gateway is available; no money was spent.
- No authorized site-builder HMAC secret or live builder facility is available.
- School profile now has an idempotent reset lifecycle locally; it needs deployment and live proof.
- Four new run-owned media records/objects remain because the API has no media delete/archive
  operation; all other API-cleanable run resources reached terminal cleanup states.

## Rollback Plan

No rollback was executed because the deployed service remained healthy and five fixes passed.
The deployment script retains exact image digests and `current`/`previous` release links and keeps
database migrations forward-only. For the next corrective deployment:

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

**NOT PRODUCTION-READY.** The current 85-operation source passes all local quality gates and repairs
media signing, delivery gates, and school-profile reset, but it is not deployed. Real OTP/payment
adapters and safe live credentials remain unspecified, as do a working external site builder and
an authorized second tenant/domain. The existing production revision therefore remains unchanged
and its prior blockers remain live.
