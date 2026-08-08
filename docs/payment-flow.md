# Payment flow

## Initiation

Only a submitted draft token holder can initiate payment. `Idempotency-Key` is unique per tenant.
The transaction copies the registration's already-snapshotted integer amount/currency and selected
plan history. A retry returns the same transaction. Payment adapters alone perform explicit provider
currency-unit conversion; core code never silently converts Rial/Toman.

The callback URL contains signed state with tenant ID, transaction ID, provider, random nonce, and
expiration. The database stores the signed state for initiation retries and only a hash of the nonce.

## Callback

Callbacks use a shared hostname and bypass normal host resolution. The application first verifies
the state signature/purpose/expiry, then establishes the signed tenant context, row-locks the
transaction and registration, checks the nonce/provider, and performs server-to-server gateway
verification. Browser parameters never establish success.

```text
INITIATED -> PENDING -> SUCCESSFUL
                     -> FAILED / CANCELLED
SUCCESSFUL -> REFUNDED (future administrative adapter operation)
```

A consumed/successful callback returns current state. The unique provider transaction identifier,
row locks, callback-consumed timestamp, and atomic registration update prevent duplicate completion.
Only successful provider verification writes registration `payment_status=SUCCESSFUL` and
`status=COMPLETED`. Failure is retry-safe and leaves the registration submit state consistent.

Production requires a concrete Iranian `PaymentGateway` adapter and its credentials/business rules.
The repository mock is accepted only in explicitly non-production settings.

