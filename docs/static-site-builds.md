# Static-site build and deployment

## Source of truth and revision

PostgreSQL/FastAPI are canonical. Each tenant has a lightweight `tenant_site_states` row with a
monotonic `content_revision`; Astro output is only a deployable projection. A transaction that
changes public static state increments the revision and creates or coalesces a
`site_build_requests` row. Draft saves and uploads never call this service.

Publication commits do not wait for a build. `PUBLISHED` and deployed state are intentionally
separate. `GET /api/v1/admin/site-build/status` reports current/deployed revisions and a safe state:
`UP_TO_DATE`, `PENDING`, `BUILDING`, `FAILED`, or `NOT_CONFIGURED`. History is available at
`/history`; `POST /rebuild` durably requests the current revision and naturally coalesces rapid
manual requests.

## Coalescing and race behavior

The tenant site-state row is locked before increment/enqueue. A partial unique index permits at most
one PENDING and one RUNNING request per tenant. A new change updates the existing PENDING target to
the newest revision. If a build is RUNNING, a separate PENDING row is retained, guaranteeing a
follow-up. Different tenants have independent rows and locks.

A success callback records `max(previous_deployed_revision, actual_revision)`, so an older build can
never move deployed state backwards or claim a newer revision. Duplicate identical success callbacks
are no-ops; conflicting results are rejected. Failure leaves deployed revision and the working site
unchanged. Retryable failures use bounded exponential backoff; attempts are capped by
`KANOON_SITE_BUILD_MAX_ATTEMPTS`.

## Worker and executor

Run the separate process:

```bash
uv run kanoon site-build-worker
```

The worker enumerates global tenant identities, then opens an ordinary RLS tenant transaction per
tenant. It claims due work with row locks/`SKIP LOCKED`, marks it RUNNING, commits, and calls a
`SiteBuildExecutor` outside HTTP workers. Multiple workers are safe; one RUNNING partial unique index
prevents simultaneous tenant builds. Leases recover crashes. Trigger requests use build request IDs
as idempotency keys, so a lease retry can safely repeat delivery.

`WebhookSiteBuildExecutor` is the production adapter; tests use `FakeSiteBuildExecutor`. Platform
administrators manage declarative per-tenant target keys and a registered canonical domain. Tenant
administrators cannot store commands, paths, repositories, environment variables, endpoints, or
secrets. Set `KANOON_SITE_BUILD_WEBHOOK_URL` and a random 32+ character
`KANOON_SITE_BUILD_HMAC_SECRET`; timeout, lease, polling, attempt, and callback-age settings are also
configurable.

Platform configuration is read/written at
`GET|PUT /api/v1/platform/tenants/{tenant_id}/site-build-config`. It contains no command, endpoint,
credential, or executable setting.

The outbound JSON contains schema version, build request/tenant infrastructure IDs, canonical
domain, opaque build/deployment target keys, target revision, snapshot path, and callback URL. The
body is signed as `HMAC-SHA256(timestamp.method.path.body)` in `X-Kanoon-Signature`; timestamps are
bounded and `Idempotency-Key` is the build request UUID.

## Astro fetch and callback

The build should reach FastAPI with `Host: <canonical_domain>` and fetch:

```text
GET /api/v1/public/blog/snapshot?requested_revision=N
```

If `content_revision` differs from N, build the returned latest state and callback with that actual
revision. No historical database snapshot is promised; the goal is latest-state convergence.

Callback:

```text
POST /api/v1/internal/site-builds/{build_request_id}/result
X-Kanoon-Timestamp: <unix-seconds>
X-Kanoon-Signature: <HMAC>

{"tenant_id":"...","status":"SUCCESSFUL","actual_revision":12}
```

Failure uses `status=FAILED`, a sanitized `error`, and `retryable`. Authentication occurs before the
signed tenant metadata is trusted. FastAPI derives tenant context from the authenticated request and
database build row, opens a normal RLS session, and verifies request/tenant/revision binding.

## Atomic deployment and availability

FastAPI never runs Node/Astro or writes Nginx document roots. The external deployment service must:

1. build into a new release directory and require a successful command;
2. verify `dist/` and its expected `index.html` (plus an optional static smoke check);
3. copy completely into `/srv/sites/<target>/releases/<revision-or-build-id>`;
4. atomically replace a temporary symlink/rename with `/srv/sites/<target>/current`;
5. callback success only after the switch, preserving the prior release for rollback.

Nginx serves `current`. Never delete/copy over the live directory. The deployment account owns
release directories; Nginx needs read/execute only; FastAPI has no filesystem access. A failed build
or validation never switches `current`, so the prior release stays online. Recovery is retry/manual
rebuild or an atomic switch to a retained prior release.
