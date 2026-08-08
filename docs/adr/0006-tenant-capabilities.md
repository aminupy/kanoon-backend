# ADR 0006: Tenant capabilities

Status: accepted.

Represent optional modules with controlled application feature keys and sparse JSON configuration.
Never branch on a tenant identity or execute tenant configuration. Relational domain data remains in
typed tables. Genuine new behavior becomes a proper module with RLS, permissions, routes, and tests.

