# ADR 0008: FastAPI CMS source of truth and Astro static projection

Status: accepted.

Store editorial content, publication state, audit history, and tenant media relationships in the
shared PostgreSQL/FastAPI system. Treat each tenant's Astro `dist/` as a derived, replaceable static
projection identified by a monotonic content revision. Public changes durably enqueue a coalesced
PostgreSQL build request; HTTP publication never runs or waits for Astro.

Storing Markdown/content in each frontend repository was rejected. It would split the source of
truth across repositories, make non-technical editing/media authorization harder, weaken shared RLS
and audit guarantees, and couple content recovery to deployments. Rendering on every request was
also rejected because the fixed frontend architecture is pure SSG behind Nginx.

Publication and deployment state remain separate: valid CMS content may be published while the
deployed projection is temporarily stale. The external builder validates a complete release and
atomically switches Nginx's live symlink; failure preserves the previous site.
