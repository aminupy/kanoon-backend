# ADR 0001: Shared-schema multi-tenancy

Status: accepted.

Use one PostgreSQL database and schema, with `tenant_id` on every owned row. This minimizes
operational/migration overhead across many branches while allowing transactional invariants across
modules. Database-per-tenant and schema-per-tenant were rejected because they multiply upgrades,
pooling, observability, and recovery work. The decision requires RLS and composite tenant keys.

