# ADR 0004: Modular monolith

Status: accepted.

Deploy one FastAPI application with domain-owned modules and a shared transaction boundary.
Microservices would add distributed transactions, duplicated tenancy/security plumbing, and
operational cost without an independent scaling or ownership requirement. Module boundaries leave a
future extraction path if evidence later justifies one.

