# Architecture

## Shape and dependency direction

This repository is a modular monolith. `core` owns infrastructure, `tenancy` owns routing and
capabilities, identity lives in `auth`, and business modules own their mappings, schemas, services,
and routes. Route functions validate/translate HTTP; services own state transitions; repository or
service query code owns persistence. Modules share one transaction when an invariant spans them.

The data-plane request path is:

```text
gateway -> request/error/logging middleware -> hostname resolution
        -> TenantContext -> tenant transaction + SET LOCAL tenant
        -> authentication/feature/permission dependencies -> thin route -> service -> PostgreSQL
```

Platform authentication is global. A platform administrator receives a global token for platform
operations. When acting on tenant data, the application opens an explicit tenant transaction; it
does not globally disable RLS.

## HTTP surfaces

`app.main:app` is the Internet-facing data plane. It registers public, tenant-admin, and required
authenticated infrastructure callback routes, but no `/api/v1/platform/*` route. It resolves tenant
context from Host and applies dynamic tenant CORS.

`app.control_plane:app` is the operator control plane. It registers only platform auth and platform
administration plus health/docs. It does not run tenant-domain resolution or public tenant CORS;
platform administrators explicitly address tenants and services enter ordinary RLS tenant sessions
when accessing owned rows. Shared construction lives in `app.application`, so this is two process
surfaces of one modular monolith, not two services. See [deployment](deployment.md) and ADR 0009.

## Modules

- `tenancy`: tenants, global domains, profiles, normalized contacts, capabilities, platform APIs.
- `auth`: Argon2id identities, tenant memberships, permission mapping, access tokens, rotated and
  hashed refresh tokens, database-backed login throttling.
- `media`: generated object keys, presigned POST policies, S3 metadata validation, signed downloads.
- `content`: banners, common NEWS/ANNOUNCEMENT/BLOG posts, honors/categories, staff, contact
  requests, sample exams, gallery, public bootstrap and administration.
- `exams`: offerings, integer/currency pricing, tenant-safe many-to-many association.
- `registrations` and `otp`: draft state machine, versioned JSON Schema answers, exactly two
  normalized contacts, capacity/duplicate locking, provider-independent verification.
- `payments`: amount snapshots, idempotent initiation, signed callback state, provider verification.
- `audit`: tenant-scoped append-oriented administrative/financial records without secret/OTP data.
- `blog`: structured ProseMirror JSON, safe deterministic rendering, explicit publication, and
  tenant-safe media references on the existing common post model.
- `site_builds`: generic tenant revisions, a coalesced PostgreSQL outbox, separate worker, HMAC
  webhook execution/results, and deployment status.

## Media

The API issues an S3 presigned POST with an exact generated key, MIME condition, and byte limit.
Completion uses `HEAD` to compare the stored content length and content type before marking metadata
READY. Public access redirects to a short-lived signed download. A production adapter may insert
quarantine/malware scanning between PENDING and READY without changing domain relationships.
Public content stores only `/api/v1/public/media/{id}`; each request obtains a fresh inline redirect,
so static HTML never contains an expiring object-store signature.

## Operational characteristics

There is one deployable application and one PostgreSQL database. Transactions, row locks, unique
constraints, composite foreign keys, and PostgreSQL advisory locks handle concurrency; no process
memory is an authority for payments, registration capacity, OTP quotas, or identity. Structured
request logs include request/tenant/route/status/duration but no request bodies or normal PII.

FastAPI/PostgreSQL are the CMS source of truth. Astro sites are independently built, atomically
deployed projections. See [static-site builds](static-site-builds.md) and ADR 0008.
