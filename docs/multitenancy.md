# Multi-tenancy and the isolation boundary

## Resolution

`tenant_domains` is a global routing table with globally unique normalized hostnames. Normalization
lowercases, removes a port/trailing dot, and applies IDNA ASCII encoding. An active domain maps to a
tenant. Unknown/inactive domains and suspended tenants receive generic unavailable responses; there
is no default tenant. Public payloads and headers cannot provide a tenant ID.

Forwarded hosts are ignored unless both forwarded-host trust is enabled and the direct peer IP is
inside a configured proxy CIDR. The trusted proxy must replace client-supplied forwarding headers.

## Application context and transaction

Middleware creates an immutable `TenantContext`. Tenant routes obtain a session only through the
tenant dependency. `Database.tenant_session` starts a transaction, selects the restricted role, and
executes:

```sql
SELECT set_config('app.current_tenant_id', :tenant_id, true);
```

The third argument makes it transaction-local. Commit/rollback clears it before the pooled
connection is reused. Tests force a one-connection pool and prove A -> no-context -> B reuse.

## PostgreSQL RLS

Every tenant table has this conceptual policy:

```sql
ALTER TABLE example ENABLE ROW LEVEL SECURITY;
ALTER TABLE example FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON example
USING (
  tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid
)
WITH CHECK (
  tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid
);
```

Missing/cleared settings evaluate to NULL and fail closed. `FORCE` also subjects the table owner to
RLS where PostgreSQL otherwise permits owner bypass. The normal role is not superuser, table owner,
or `BYPASSRLS`. Migration credentials are distinct from web credentials. Superusers always bypass
RLS and must never run the web process.

## Tenant-aware relationships

Tenant entities expose `UNIQUE (tenant_id, id)`. Child relations carry the same `tenant_id` and use
composite foreign keys, for example:

```sql
FOREIGN KEY (tenant_id, image_id)
REFERENCES media_assets (tenant_id, id)
```

Thus an application defect cannot connect tenant A's row to tenant B's media, price, exam,
registration, category, album, or payment object. The global `school_directory_entries` table is
intentionally not a tenant table; it describes an applicant's current/previous educational school,
not an application tenant.

## Adding a tenant-owned table checklist

1. Add `tenant_id UUID NOT NULL REFERENCES tenants(id)` and `UNIQUE (tenant_id, id)`.
2. Put `tenant_id` first in indexes supporting tenant access patterns.
3. Use composite tenant-aware foreign keys for every tenant-owned parent.
4. Add `ENABLE ROW LEVEL SECURITY`, `FORCE ROW LEVEL SECURITY`, and the fail-closed policy in
   Alembic; add the table to the migration's grants.
5. Never accept its tenant ID in a public/admin body; set it from `TenantContext`.
6. Access it only inside a tenant transaction; background jobs must carry an authenticated tenant
   work item and open a fresh tenant transaction per item.
7. Add isolation tests for read, insert/reference, update, delete, missing context, and pool reuse.
8. Run `alembic check` and the schema audit before merge.

## Static build workers

Build tables remain tenant-owned and use the same forced RLS policy. The worker does not bypass RLS:
it discovers global tenant IDs, then opens one fresh `tenant_session` per work stream. Normal
admin/public content and build requests still derive tenant only from Host. The sole exception is the
internal result callback: after HMAC/timestamp verification, signed tenant metadata is checked
against the referenced durable build row before establishing the usual tenant transaction.
