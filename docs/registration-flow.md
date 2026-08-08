# Registration flow

## States

```text
DRAFT / PHONE_VERIFICATION_REQUIRED
  -> PHONE_VERIFIED -> READY_FOR_SUBMISSION
  -> SUBMITTED -> PAYMENT_PENDING -> COMPLETED
  -> CANCELLED
```

Draft creation validates the tenant's open exam and selected associated published price, snapshots
integer amount/currency, selects the current versioned form definition, and returns a high-entropy
token once. Only its SHA-256 digest is stored. The `Draft` authorization scheme is checked with a
constant-time comparison and is still constrained by the request's domain/RLS tenant. Token rotation
revokes the old value immediately.

PATCH accepts partial common typed fields. It never accepts tenant or payment status. Changing the
canonical mobile clears `phone_verified_at` and invalidates active OTP challenges. `extra_answers`
is validated at submission against the exact immutable JSON Schema version captured at creation.

Submission row-locks the registration and exam. It requires all core fields, a verified current
phone, and exactly positions 1 and 2 in `registration_contacts`. The exam lock serializes capacity
checks. `UNIQUE (tenant_id, exam_offering_id, national_code)` rejects duplicates. Repeating a
successful submission returns the already-submitted row without duplicating side effects.

Canonical dates are PostgreSQL `DATE`; timestamps are UTC `TIMESTAMPTZ`. Mobile, postal and national
codes are strings. Jalali presentation is a frontend concern.

## OTP

Six-digit codes use cryptographic randomness and keyed hashes; plaintext exists only long enough to
call the provider and is never logged/stored. Challenges expire, have a configurable attempt limit,
resend cooldown, one-time consumption, and invalidation on phone change. PostgreSQL advisory locks
serialize per-tenant, per-phone, and per-IP quotas across processes.

