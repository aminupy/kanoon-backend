# GitHub Actions production CI/CD

The workflow in `.github/workflows/ci.yml` tests every push and pull request. A push to `main`
continues only after all gates pass: it builds the application image, publishes it to GHCR with an
immutable digest, and deploys that exact digest to production. Pull requests and non-`main`
branches never receive production credentials and never deploy.

The `production` GitHub Environment should be restricted to the `main` branch. Enable required
reviewers if deployments should require approval; leave reviewers disabled for fully automatic
deployment after every successful `main` push. The deployment job has a GitHub concurrency lock,
and the host script also uses `flock`, so two releases cannot mutate the Compose project at once.

## GitHub Environment variables

Create a GitHub Environment named `production` and add these environment variables under
**Settings → Environments → production → Environment variables**:

| Name | Example | Purpose |
| --- | --- | --- |
| `PRODUCTION_URL` | `https://kanoon.esaminu.ir` | Link displayed by GitHub for the environment. |
| `DEPLOY_HOST` | `kanoon.esaminu.ir` | SSH hostname or IPv4 address. Do not include a scheme or port. |
| `DEPLOY_PORT` | `22` | SSH port. |
| `DEPLOY_USER` | `kanoon-deploy` | Dedicated unprivileged deployment account. |
| `DEPLOY_PATH` | `/opt/kanoon` | Absolute release root owned by the deployment account. |
| `DEPLOY_HEALTH_URL` | `https://kanoon.esaminu.ir/health/ready` | Public readiness URL checked after deployment and rollback. |
| `DEPLOY_OPENAPI_URL` | `https://kanoon.esaminu.ir/openapi.json` | Deployed contract compared canonically with the committed contract. |
| `DEPLOY_KEEP_RELEASES` | `5` | Release directories retained on the host; allowed range is 2–50. |
| `GHCR_DEPLOY_USERNAME` | `aminupy` | GitHub account that owns the read-only package token. |

Values are validated before any SSH connection. Hostnames, paths, URLs, image references, and
counts deliberately accept a narrow character set so an altered repository variable cannot inject
a remote shell command.

With GitHub CLI authenticated for `aminupy/kanoon-backend`, the non-secret example values can be
created as follows. Replace the SSH host/user/port if production differs:

```bash
gh variable set PRODUCTION_URL --env production --body https://kanoon.esaminu.ir
gh variable set DEPLOY_HOST --env production --body kanoon.esaminu.ir
gh variable set DEPLOY_PORT --env production --body 22
gh variable set DEPLOY_USER --env production --body kanoon-deploy
gh variable set DEPLOY_PATH --env production --body /opt/kanoon
gh variable set DEPLOY_HEALTH_URL --env production --body https://kanoon.esaminu.ir/health/ready
gh variable set DEPLOY_OPENAPI_URL --env production --body https://kanoon.esaminu.ir/openapi.json
gh variable set DEPLOY_KEEP_RELEASES --env production --body 5
gh variable set GHCR_DEPLOY_USERNAME --env production --body aminupy
```

## GitHub Environment secrets

Add exactly these secrets under **Settings → Environments → production → Environment secrets**:

| Name | Required value |
| --- | --- |
| `DEPLOY_SSH_PRIVATE_KEY` | Complete private half of a dedicated Ed25519 deployment key. Do not add a passphrase because the non-interactive runner cannot unlock it. |
| `DEPLOY_SSH_KNOWN_HOSTS` | Pinned `known_hosts` line for `DEPLOY_HOST` and `DEPLOY_PORT`, captured through a trusted channel and verified against the server host-key fingerprint. |
| `GHCR_DEPLOY_TOKEN` | Package-read token for `GHCR_DEPLOY_USERNAME`; grant only the access needed to pull `ghcr.io/aminupy/kanoon-backend`. |

Load secret values from protected files or standard input; never put a secret in `--body`, where it
would enter shell history and the process argument list:

```bash
gh secret set DEPLOY_SSH_PRIVATE_KEY --env production < /secure/path/kanoon-deploy-key
gh secret set DEPLOY_SSH_KNOWN_HOSTS --env production < /secure/path/kanoon-known-hosts
gh secret set GHCR_DEPLOY_TOKEN --env production < /secure/path/ghcr-read-token
```

`GITHUB_TOKEN` is created automatically for each workflow run and publishes the image; do not add
it yourself. The PostgreSQL, signing, and MinIO values in the quality job are disposable CI-only
credentials scoped to isolated runner services. They are intentionally not GitHub secrets and
must never be reused outside CI.

Use a dedicated SSH key rather than a personal key. Install only its public half in the deployment
user's `authorized_keys`. Generate `DEPLOY_SSH_KNOWN_HOSTS` on a trusted operator machine or from
the server console, then compare the fingerprint with the server's host public key before adding
it to GitHub. The workflow intentionally does not run `ssh-keyscan`, because accepting a key during
the deployment would defeat host verification.

For a private GHCR package, use a token accepted by GitHub Packages with package read access. If
the account requires SSO authorization, authorize the token for the organization. The token is
piped over SSH to `docker login --password-stdin`; it is never placed in a process argument or a
release file.

## One-time production-host preparation

Install Docker Engine, the Docker Compose plugin, `curl`, `flock`, GNU `tar`, GNU coreutils, and GNU
findutils. The dedicated deployment user must be able to run Docker without interactive `sudo`,
SSH into the host non-interactively, and own the deployment root. Docker daemon access is
effectively root-equivalent, so protect and rotate this key as a privileged production credential.
For the example variables above:

```bash
sudo install -d -o amin -g kanoon-deploy -m 0750 /opt/kanoon
sudo install -d -o amin -g kanoon-deploy -m 0750 /opt/kanoon/releases
sudo install -d -o amin -g kanoon-deploy -m 0700 /opt/kanoon/shared
```

Create these two host-owned files once. They must not be committed, uploaded in a release bundle,
or stored in GitHub:

```text
/opt/kanoon/shared/.env.production
/opt/kanoon/shared/.env.production.app
```

Start from `deploy/production/compose.env.example` and `deploy/production/app.env.example`, replace
every placeholder, and set mode `0600`. The workflow checks that neither file is group/world
accessible before touching the running stack.

The Compose environment contains:

| Classification | Names |
| --- | --- |
| Non-secret | `KANOON_DATA_PLANE_PORT`, `KANOON_CONTROL_PLANE_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `KANOON_DB_APP_USER` |
| Secret | `POSTGRES_PASSWORD`, `KANOON_DB_APP_PASSWORD`, `KANOON_MIGRATION_DATABASE_DSN` |
| Managed by deployment | `KANOON_IMAGE`, `KANOON_APP_ENV_FILE` |

The application environment contains:

| Classification | Names |
| --- | --- |
| Non-secret | `KANOON_ENVIRONMENT`, `KANOON_DEBUG`, `KANOON_DATABASE_APPLICATION_ROLE`, `KANOON_TRUST_FORWARDED_HOST`, `KANOON_TRUSTED_PROXY_CIDRS`, `KANOON_ALLOWED_CORS_ORIGINS`, `KANOON_OTP_PROVIDER`, `KANOON_PAYMENT_PROVIDER`, `KANOON_PUBLIC_BASE_URL`, `KANOON_SITE_BUILD_WEBHOOK_URL`, `KANOON_SITE_BUILD_MAX_ATTEMPTS`, `KANOON_SITE_BUILD_LEASE_SECONDS`, `KANOON_SITE_BUILD_POLL_SECONDS`, `KANOON_S3_ENDPOINT_URL`, `KANOON_S3_PUBLIC_ENDPOINT_URL`, `KANOON_S3_REGION`, `KANOON_S3_BUCKET` |
| Secret | `KANOON_DATABASE_DSN`, `KANOON_SIGNING_KEY`, `KANOON_SITE_BUILD_HMAC_SECRET`, `KANOON_S3_ACCESS_KEY`, `KANOON_S3_SECRET_KEY`, plus provider-specific OTP/payment credentials once concrete adapters define them |

Keep the migration-owner DSN only in `.env.production`. The long-running application receives the
restricted runtime DSN. URL-encode reserved password characters inside DSNs. Back up the database
using an independently tested process before enabling the first automatic deployment.

## What a deployment does

Each successful `main` push produces `ghcr.io/aminupy/kanoon-backend@sha256:…`; tags are published
for operator convenience, but deployment uses only the digest. The workflow sends a small release
bundle containing Compose, the database initializer, the deployment verifier, and the committed
OpenAPI document. It never sends an environment file.

The host script then:

1. locks `/opt/kanoon/deploy.lock`;
2. validates protected files and the Compose model;
3. pulls the immutable image and verifies its OCI revision label against the Git commit;
4. runs Alembic through Compose before allowing dependent services to start;
5. waits for production readiness;
6. compares deployed and committed OpenAPI documents canonically;
7. atomically updates `current` and `previous` release links; and
8. retains the configured number of releases.

If an application, health, or OpenAPI check fails after rollout starts, the script restores the
previous application image. It does not automatically downgrade the database. Every migration must
therefore be backward-compatible with the immediately preceding application release (expand,
deploy, then contract in a later release). A database restore remains an explicit operator action.
On the first managed release, no safe previous digest exists; a failed application is stopped
instead of being left online.

## Required preflight before enabling automatic deployment

The repository currently has no concrete external `OTPProvider` or `PaymentGateway` adapter in the
default application factory. Production configuration correctly rejects mocks, and
`app.main:create_app()` rejects `external` settings unless concrete adapters are supplied in code.
Consequently, the first production deployment will fail closed until those real adapters and their
provider-specific settings are implemented. Do not change production back to mock providers to
make the pipeline green.

Also verify the host Caddy configuration, external object-storage endpoint, bucket policy, backup
and restore procedure, and PostgreSQL 18 migration plan before merging the workflow to `main`.

## Branch and repository settings

Protect `main` and require the **Test, contract, and migration gates** and **Container build gate**
jobs before merge. Disable direct pushes if every production change should pass review. Keep
Actions permission at
**Read repository contents and packages**; the image job elevates only its own `packages: write`
permission. Do not enable “Allow GitHub Actions to create and approve pull requests.”

To stop deployments without changing code, add a required reviewer to the `production`
environment or disable the workflow. After confirming the prior application is compatible with the
forward database schema, an authorized host operator can perform the locked, readiness-checked,
OpenAPI-checked application rollback with:

```bash
DEPLOY_ROOT=/opt/kanoon \
HEALTH_URL=https://kanoon.esaminu.ir/health/ready \
OPENAPI_URL=https://kanoon.esaminu.ir/openapi.json \
/opt/kanoon/current/deploy/production/rollback.sh
```

This swaps the `current` and `previous` links only after verification and never downgrades the
database.
