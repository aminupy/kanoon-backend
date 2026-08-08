# Security model

## Trust boundaries

- The Internet-facing data-plane ASGI application does not register platform routes. Platform APIs
  exist only in a separately supervised loopback/private control-plane listener.

- The gateway authenticates no tenant; it preserves the original Host and removes untrusted
  forwarding headers. FastAPI resolves Host against the global active-domain table.
- Browser/admin access tokens are short-lived. Refresh values are opaque, hashed, rotated, and
  family-revoked on reuse. Argon2id hashes passwords.
- Tenant permissions are centralized role-to-permission mappings. Tenant IDs in bodies do not grant
  scope. Platform tokens cannot be used as tenant tokens without explicitly selecting a tenant.
- Registration draft tokens authorize one row only and remain subject to domain and RLS checks.
- Payment success comes only from the configured gateway's server verification method.
- Site-build callbacks require a timestamp-bounded HMAC over method, path, and exact body. Signed
  tenant metadata must match the durable request before it can establish worker tenant context.

Control-plane network isolation does not replace authentication. Access tokens already separate
surfaces with signed `tenant_id` and `platform_admin` claims: platform dependencies require a global
token (`tenant_id` absent), the platform-admin claim, and a fresh database check that the user remains
active and privileged. Tenant tokens cannot satisfy that dependency. A new JWT audience was not
added because it would invalidate active sessions while duplicating these enforced claims; add an
explicit versioned audience during a planned token migration if independent signing/audience policy
is later required.

## Sensitive data

Request logs contain no bodies and therefore no passwords, OTPs, national codes, addresses, or
phones. Errors expose stable codes and sanitized validation locations/messages. Audit metadata holds
action identifiers and changed field names, not credentials or routine PII. Production exception
responses never include stack traces.

Uploads have backend-generated keys, exact MIME/extension allowlists, presigned size conditions, and
post-upload metadata verification. S3 credentials and signing keys come from the environment/secret
manager. Database BLOBs are prohibited.

Blog rich text is structured JSON, not administrator HTML. A bounded node/mark allowlist rejects
scripts, arbitrary embeds/iframes/fields, unsafe URL schemes, and malformed/deep documents. The
server escapes text/attributes and emits only controlled HTML. Public static documents contain stable
media API identities, never object credentials or expiring presigned URLs.

Only platform administrators set declarative build target keys and canonical registered domains.
Tenant administrators cannot configure commands, repository credentials, paths, webhooks, secrets,
or environment variables. FastAPI never executes frontend tooling or writes Nginx roots.

## HTTP deployment

Use TLS, HSTS, body/time limits, bot/DDoS controls, and access-log redaction at the gateway. The app
adds nosniff, frame denial, referrer, permissions-policy, request ID, and strict dynamic CORS headers.
Same-origin `/api` proxying is preferred. Bearer-token admin APIs are not cookie-authenticated, so
CSRF is not the primary control; if deployment moves tokens into cookies, add SameSite/secure cookie
and CSRF-token enforcement before that change.

Mock OTP/payment providers are rejected by production settings. The mock OTP exposes last codes only
inside its in-process adapter for tests and never through an API or log.

The reverse proxy targets only data-plane port 8000. Docker publishes control port 8001 only on
`127.0.0.1`, with no public hostname or proxy router. Operators use an SSH tunnel and still log in
normally. See [HTTP surface deployment](deployment.md).
