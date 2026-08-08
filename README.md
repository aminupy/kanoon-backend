# Kanoon backend

Production-oriented FastAPI modular monolith for many institute branch websites. A request's
hostname selects a tenant; PostgreSQL row-level security and tenant-aware foreign keys remain the
independent isolation boundary if application filtering is defective.

## Architecture at a glance

- Separate FastAPI/Pydantic v2 data-plane (`public`/`admin`) and loopback control-plane (`platform`)
  ASGI applications from the same modular monolith.
- SQLAlchemy 2 async sessions using psycopg 3. Every tenant session is one transaction with
  `SET LOCAL ROLE kanoon_app` and transaction-local `app.current_tenant_id`.
- Shared PostgreSQL schema; every tenant-owned table has `tenant_id`, RLS, `FORCE ROW LEVEL
  SECURITY`, and composite foreign keys for tenant-owned relationships.
- S3-compatible object storage through an adapter; PostgreSQL stores metadata only.
- Capability rows control optional modules. There are no tenant identity branches.
- Opaque hashed draft tokens, configurable OTP delivery, and payment-gateway adapters.
- Signed payment callback state establishes tenant context on the shared callback hostname.

More detail: [architecture](docs/architecture.md), [multi-tenancy](docs/multitenancy.md),
[registration](docs/registration-flow.md), [payments](docs/payment-flow.md), and
[security](docs/security.md). Blog lifecycle and durable Astro projection details are in
[blog](docs/blog.md) and [static-site builds](docs/static-site-builds.md).
HTTP process/network composition is documented in [deployment](docs/deployment.md).

## Local setup

Requirements: Docker/Podman Compose and `uv 0.11.33` (the lock also works with compatible uv 0.11.x).

```bash
cp .env.example .env
docker compose up -d postgres minio
uv sync --frozen --all-groups
uv run alembic upgrade head
KANOON_BOOTSTRAP_PASSWORD='use-a-random-development-value' uv run kanoon bootstrap \
  --email admin@example.test \
  --tenant-name 'Development School' \
  --tenant-slug development-school \
  --tenant-domain school.localhost
make run
# In a second terminal:
make run-control
```

Map `school.localhost` to `127.0.0.1` if the local resolver does not already resolve `*.localhost`.
Data-plane OpenAPI is at `http://school.localhost:8000/docs` outside production. Control-plane
OpenAPI is at `http://127.0.0.1:8001/docs`; platform authentication is still required for APIs.

The bootstrap password is read from a one-use environment value or an interactive hidden prompt;
the repository never installs a predictable password. Remove it from the environment after use.

## Configuration

Settings use the `KANOON_` prefix and are typed in `app/core/config.py`. Production startup rejects
debug mode, short signing keys, mock OTP, and mock payment settings. Supply concrete `OTPProvider`
and `PaymentGateway` adapters to `create_app`; vendor credentials remain environment/secret-manager
inputs. `.env.example` contains local non-secret defaults.

Prefer same-origin `https://school.example/api/...`. If the API is cross-origin, CORS accepts only
configured platform origins or active domains owned by the already-resolved tenant.

## Database and roles

Alembic must connect as the migration owner. The web process must connect with a role that can
`SET ROLE kanoon_app`, or directly as an equivalently restricted LOGIN role. `kanoon_app` is
`NOSUPERUSER NOBYPASSRLS` and is not a table owner. Do not give application credentials to Alembic.

```bash
uv run alembic upgrade head
uv run alembic check
```

The initial migration creates the no-login development role and all RLS policies. Production DBAs
may pre-create the role/login and manage its password through the platform secret system.

## Quality commands

```bash
make lint
make typecheck
make test
KANOON_TEST_DATABASE_DSN='postgresql+psycopg://...' make test-integration
make migration-check
```

Integration tests require real PostgreSQL. With no DSN they use Testcontainers; CI supplies a
dedicated PostgreSQL service explicitly. SQLite is never used for isolation tests.

## Proxy requirements

The gateway must preserve the original school `Host`. By default forwarded host headers are
ignored. If a trusted proxy must replace Host, enable `KANOON_TRUST_FORWARDED_HOST=true`, list only
the immediate proxy networks in `KANOON_TRUSTED_PROXY_CIDRS`, and configure the proxy to replace
(not append client-controlled values to) `X-Forwarded-Host`. Unknown hosts never use a fallback
tenant.

Terminate TLS at the gateway, enforce request/body limits, add HSTS there, and preserve
`X-Request-ID` or allow the application to generate one.
