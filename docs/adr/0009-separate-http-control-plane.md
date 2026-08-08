# ADR 0009: Separate data-plane and control-plane HTTP surfaces

Status: accepted.

Keep one modular-monolith codebase and PostgreSQL database, but compose two explicit FastAPI ASGI
applications. The Internet-facing data plane contains tenant public/admin functionality and no
`/api/v1/platform/*` routes. The control plane contains platform authentication and administration,
runs as a separate process from the same image, and is published only on host loopback for SSH
tunneling.

Both applications share configuration, database infrastructure, error handling, security headers,
request logging, authentication primitives, domain services, and mappings. Only router composition,
tenant/CORS middleware, readiness dependencies, documentation title, and network listener differ.

Hiding OpenAPI operations, Nginx deny rules, authentication alone, and firewall rules were rejected
as the primary boundary because the privileged routes would remain reachable in the public ASGI
application. A public control hostname was rejected because current operators can use SSH loopback
tunneling. A separate repository/service/database was rejected because it would duplicate domain
logic, tenancy invariants, transactions, migrations, and operations without providing a useful
business boundary.

Loopback/private networking is defense in depth, not identity. Platform authentication, global-token
claims, live platform-admin database verification, restricted application DB role, and tenant RLS
remain mandatory.
