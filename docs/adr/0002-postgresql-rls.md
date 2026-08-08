# ADR 0002: PostgreSQL row-level security

Status: accepted.

Application filters are insufficient as a security boundary. Each tenant transaction sets a local
tenant setting; every owned table has fail-closed RLS plus `FORCE ROW LEVEL SECURITY`. The web role
is neither owner nor `BYPASSRLS`. This contains ordinary route/repository filter defects and is
verified using real PostgreSQL and pooled connections.

