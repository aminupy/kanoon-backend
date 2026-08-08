# ADR 0007: Typed registration core plus versioned custom answers

Status: accepted.

Keep identity, contact, exam, payment, and submission fields as constrained relational columns.
Limited school-specific questions use declarative JSON Schema definitions and JSON answers captured
against an immutable definition/version. EAV and fully dynamic registration documents were rejected
because they weaken constraints, queries, migrations, and historical validation.
