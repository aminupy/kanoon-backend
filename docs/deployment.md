# HTTP surface deployment

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

Start both same-image processes with Compose:

```bash
docker compose up -d backend backend-control-plane
```

The existing production requirements for concrete OTP/payment adapters and external secrets still
apply to the data-plane composition entrypoint.

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
