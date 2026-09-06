#!/usr/bin/env bash
set -Eeuo pipefail
umask 027

required=(DEPLOY_ROOT HEALTH_URL OPENAPI_URL)
for variable in "${required[@]}"; do
  if [[ -z "${!variable:-}" ]]; then
    printf 'Required rollback variable is missing: %s\n' "$variable" >&2
    exit 2
  fi
done

[[ "$DEPLOY_ROOT" =~ ^/[A-Za-z0-9._/-]+$ ]]
[[ "$HEALTH_URL" =~ ^https://[A-Za-z0-9._:/-]+$ ]]
[[ "$OPENAPI_URL" =~ ^https://[A-Za-z0-9._:/-]+$ ]]

releases_root="$DEPLOY_ROOT/releases"
shared_root="$DEPLOY_ROOT/shared"
current_link="$DEPLOY_ROOT/current"
previous_link="$DEPLOY_ROOT/previous"
compose_env="$shared_root/.env.production"
app_env="$shared_root/.env.production.app"
lock_file="$DEPLOY_ROOT/deploy.lock"

if [[ ! -L "$current_link" || ! -L "$previous_link" ]]; then
  printf 'Both current and previous release links are required for rollback\n' >&2
  exit 2
fi
current_release="$(readlink --canonicalize "$current_link")"
rollback_release="$(readlink --canonicalize "$previous_link")"
for release in "$current_release" "$rollback_release"; do
  if [[ "$release" != "$releases_root/"* || ! -d "$release" ]]; then
    printf 'Release link resolves outside the release root\n' >&2
    exit 2
  fi
done
if [[ "$current_release" == "$rollback_release" ]]; then
  printf 'Current and previous releases are identical\n' >&2
  exit 2
fi

release_env="$rollback_release/release.env"
compose_file="$rollback_release/docker-compose.production.yml"
for path in "$release_env" "$compose_file" "$rollback_release/openapi.json" "$compose_env" "$app_env"; do
  if [[ ! -f "$path" ]]; then
    printf 'Required rollback file is missing: %s\n' "$path" >&2
    exit 2
  fi
done

rollback_image="$(sed -n 's/^KANOON_IMAGE=//p' "$release_env")"
rollback_revision="$(sed -n 's/^RELEASE_ID=//p' "$release_env")"
[[ "$rollback_image" =~ ^(ghcr\.io/[a-z0-9._/-]+@sha256:[a-f0-9]{64}|kanoon-backend:sha-[a-f0-9]{40})$ ]]
[[ "$rollback_revision" =~ ^[a-f0-9]{40}$ ]]

touch "$lock_file"
chmod 600 "$lock_file"
exec 9>"$lock_file"
if ! flock --exclusive --wait 300 9; then
  printf 'Timed out waiting for the production deployment lock\n' >&2
  exit 3
fi

export KANOON_IMAGE="$rollback_image"
export KANOON_APP_ENV_FILE="$app_env"
compose=(
  docker compose
  --project-name kanoon-production
  --env-file "$compose_env"
  --file "$compose_file"
)
"${compose[@]}" config --quiet
if [[ "$rollback_image" == ghcr.io/* ]]; then
  "${compose[@]}" pull backend backend-control-plane site-build-worker
else
  docker image inspect "$rollback_image" >/dev/null
fi

actual_revision="$(
  docker image inspect "$rollback_image" \
    --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}'
)"
if [[ "$actual_revision" != "$rollback_revision" ]]; then
  printf 'Rollback image revision label does not match release metadata\n' >&2
  exit 4
fi

# Database state remains at the forward migration. Rollback-compatible migrations are mandatory.
"${compose[@]}" up --detach --no-deps backend backend-control-plane site-build-worker
for attempt in {1..30}; do
  if curl --fail --silent --show-error --max-time 5 "$HEALTH_URL" >/dev/null; then
    break
  fi
  if ((attempt == 30)); then
    printf 'Rollback readiness check did not become healthy\n' >&2
    exit 5
  fi
  sleep 2
done

docker run --rm \
  --user "$(id -u):$(id -g)" \
  --volume "$rollback_release:/release:ro" \
  "$rollback_image" \
  python /release/deploy/production/verify_openapi.py \
  --expected /release/openapi.json \
  --actual-url "$OPENAPI_URL"

temporary_current="$current_link.tmp.$$"
temporary_previous="$previous_link.tmp.$$"
ln --symbolic "$rollback_release" "$temporary_current"
ln --symbolic "$current_release" "$temporary_previous"
mv --force --no-target-directory "$temporary_previous" "$previous_link"
mv --force --no-target-directory "$temporary_current" "$current_link"

printf 'Rollback succeeded: revision=%s image=%s\n' "$rollback_revision" "$rollback_image"
