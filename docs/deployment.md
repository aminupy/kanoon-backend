# HTTP surface deployment

The automated GitHub Actions release procedure, one-time host preparation, and exact GitHub
variables/secrets are documented in [`docs/github-cicd.md`](github-cicd.md).

## Processes and network exposure

The modular monolith has two ASGI applications built from the same image, code, settings, models,
services, and PostgreSQL database:

| Process | ASGI application | Host exposure | Purpose |
| --- | --- | --- | --- |
| Data plane | `app.main:app` | proxy-facing port 8000 | tenant public/admin APIs and authenticated internal callbacks |
| Control plane | `app.control_plane:app` | host loopback port 8001 only | platform authentication and platform administration |

Compose runs these as `backend` and `backend-control-plane`. The control process listens on
`0.0.0.0:8001` inside its container because container loopback is not host loopback, but Docker must
publish it exactly as:

```yaml
ports:
  - "127.0.0.1:8001:8001"
```

Never replace that mapping with `8001:8001`. The host firewall should also reject external 8001,
but firewall policy is secondary defense. The control service explicitly sets
`traefik.enable=false`. If another proxy uses automatic discovery, exclude the control service.

The Internet reverse proxy routes only to `backend:8000`. This repository contains no Nginx or
Traefik routing configuration; the production gateway configuration must not define a router,
hostname, TLS certificate, or public DNS record for the control plane.

The repository data-plane Caddy template is `deploy/Caddyfile.example`. Its canonical virtual host
preserves `Host`, removes client-supplied `X-Forwarded-Host`, and has an explicit TLS catch-all that
returns non-cacheable HTTP 421. Validate the rendered production Caddy configuration before reload;
keep the previous configuration available for immediate rollback.

Start both same-image processes with Compose:

```bash
docker compose up -d backend backend-control-plane
```

The existing production requirements for concrete OTP/payment adapters and external secrets still
apply to the data-plane composition entrypoint.

## Production Compose stack

`docker-compose.production.yml` is the standalone production topology. It uses the
`postgres:18-alpine` image pinned by digest, a one-shot Alembic migration job, the data plane, the
loopback-only control plane, and the site-build worker. PostgreSQL has no published host port. The
data plane is also bound to host loopback for a host-managed reverse proxy. Update the PostgreSQL
digest only as a reviewed infrastructure change with a backup and restore test; application pushes
must not silently upgrade the database image.

PostgreSQL 18 uses `/var/lib/postgresql/18/docker` as `PGDATA` and declares its volume at
`/var/lib/postgresql`; the production Compose file therefore mounts its named volume at the parent
path. Never attach an existing PostgreSQL 17 data volume directly to the PostgreSQL 18 service.
Use a tested `pg_upgrade` procedure or logical dump/restore, with a verified backup and rollback
copy.

Create the two protected environment files on the production host:

```bash
cp deploy/production/compose.env.example .env.production
cp deploy/production/app.env.example .env.production.app
chmod 600 .env.production .env.production.app
```

`.env.production` is used only for Compose interpolation and contains the database initialization
and migration-owner inputs. `.env.production.app` is passed to application containers and must
contain only the restricted runtime DSN and application settings. URL-encode reserved password
characters inside both DSNs. Use different, randomly generated passwords of at least 24 characters
for the owner and runtime roles. Never place the owner DSN in the application environment file.

Set `KANOON_IMAGE` to an immutable application image digest. Replace every placeholder and verify
that the image wires concrete production OTP and payment adapters; the repository intentionally
refuses to start the data plane with mocks in production.

Validate and start the stack:

```bash
docker compose --env-file .env.production -f docker-compose.production.yml config --quiet
docker compose --env-file .env.production -f docker-compose.production.yml pull
docker compose --env-file .env.production -f docker-compose.production.yml up -d
docker compose --env-file .env.production -f docker-compose.production.yml ps
```

On the first initialization, `deploy/postgres/init/00-kanoon-roles.sh` creates the non-login,
non-owner `kanoon_app` RLS role and a restricted runtime login that may assume it. The script runs
only for an empty data directory. For an existing database, a DBA must provision and audit those
roles before migrations. The migration job alone receives `KANOON_MIGRATION_DATABASE_DSN`; all
long-running application processes use `KANOON_DATABASE_DSN` from the application environment.

Take database backups outside this Compose stack and test restores regularly. A named volume is
persistence, not a backup.

## Operator access

Open a tunnel from the operator workstation:

```bash
ssh -N -L 8001:127.0.0.1:8001 user@server
```

Then open `http://127.0.0.1:8001/docs`. The tunnel does not authenticate the operator to Kanoon;
normal `/api/v1/platform/auth/login` authentication and platform authorization remain mandatory.

A future private VPN or internal control-plane domain can route to the same control ASGI listener,
provided it is not Internet-accessible and independently terminates TLS. No domain/service/database
split is needed. Control-plane CORS is currently disabled; add a separate restrictive setting only
if a real browser-based operator frontend is introduced.

## Local development

Run the surfaces in separate terminals:

```bash
make run
make run-control
```

These use typed `KANOON_DATA_PLANE_HOST/PORT` and `KANOON_CONTROL_PLANE_HOST/PORT` settings. The
native control default is `127.0.0.1:8001`.

Data-plane docs are available at the tenant host's `/docs` outside production. Production preserves
the existing policy of hiding data-plane Swagger UI. Regardless of documentation policy, the data
application registers no `/api/v1/platform/*` route and its OpenAPI contains none. Control-plane
Swagger/OpenAPI remain at `/docs` and `/openapi.json` on the isolated listener.

Both applications expose non-sensitive `/health/live` and `/health/ready`. Data readiness checks
PostgreSQL and object storage; control readiness checks PostgreSQL only. Public gateway health does
not depend on the control process.

## Object-storage endpoints

Configure the backend's private transport separately from the browser-visible S3 gateway:

```dotenv
KANOON_S3_ENDPOINT_URL=http://storage.service.internal:8333
KANOON_S3_PUBLIC_ENDPOINT_URL=https://storage.example.com
KANOON_S3_BUCKET=kanoon
```

The first URL is used for health checks, object inspection, deletion, and bucket administration. It
may be private HTTP on a trusted service network. The second URL is used by boto3 when calculating
presigned uploads and downloads, must be reachable from users' browsers, and must use HTTPS in
production. Both endpoints must reach the same logical S3 service and bucket.

The public storage proxy must preserve the original Host, path, query string, request body, and
method; changing signature-bound request components produces S3 signature errors. Configure the S3
bucket/gateway CORS policy with the exact tenant and administration frontend origins that upload or
fetch objects. Do not use a wildcard origin with credentials. Editing `.env` does not alter an
already-created container; recreate the data-plane container after changing these values.
