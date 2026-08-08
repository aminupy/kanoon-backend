# ADR 0003: Custom-domain tenant resolution

Status: accepted.

Resolve tenant from a normalized, globally unique, active hostname before tenant data access. Do not
accept tenant IDs from public query/header/body input and do not fall back on unknown domains.
Forwarded hosts are usable only from configured proxy CIDRs. Payment callbacks are the exception:
they establish scope from cryptographically signed callback state.

