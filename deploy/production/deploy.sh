#!/usr/bin/env bash
set -Eeuo pipefail
umask 027

required=(DEPLOY_ROOT RELEASE_ID KANOON_IMAGE HEALTH_URL OPENAPI_URL KEEP_RELEASES)
for variable in "${required[@]}"; do
  if [[ -z "${!variable:-}" ]]; then
    printf 'Required deployment variable is missing: %s\n' "$variable" >&2
    exit 2
  fi
done

[[ "$DEPLOY_ROOT" =~ ^/[A-Za-z0-9._/-]+$ ]]
[[ "$RELEASE_ID" =~ ^[a-f0-9]{40}$ ]]
[[ "$KANOON_IMAGE" =~ ^(ghcr\.io/[a-z0-9._/-]+@sha256:[a-f0-9]{64}|kanoon-backend:sha-[a-f0-9]{40})$ ]]
[[ "$HEALTH_URL" =~ ^https://[A-Za-z0-9._:/-]+$ ]]
[[ "$OPENAPI_URL" =~ ^https://[A-Za-z0-9._:/-]+$ ]]
[[ "$KEEP_RELEASES" =~ ^[0-9]+$ ]]
((KEEP_RELEASES >= 2 && KEEP_RELEASES <= 50))

releases_root="$DEPLOY_ROOT/releases"
shared_root="$DEPLOY_ROOT/shared"
release_path="$releases_root/$RELEASE_ID"
compose_file="$release_path/docker-compose.production.yml"
compose_env="$shared_root/.env.production"
app_env="$shared_root/.env.production.app"
current_link="$DEPLOY_ROOT/current"
previous_link="$DEPLOY_ROOT/previous"
lock_file="$DEPLOY_ROOT/deploy.lock"

for path in "$compose_file" "$release_path/openapi.json" "$compose_env" "$app_env"; do
  if [[ ! -f "$path" ]]; then
    printf 'Required deployment file is missing: %s\n' "$path" >&2
    exit 2
  fi
done

for secret_file in "$compose_env" "$app_env"; do
  permissions="$(stat --format='%a' "$secret_file")"
  if ((10#$permissions % 100 != 0)); then
    printf 'Secret file must not be group/world accessible: %s\n' "$secret_file" >&2
    exit 2
  fi
done

mkdir -p "$releases_root" "$shared_root"
touch "$lock_file"
chmod 600 "$lock_file"
exec 9>"$lock_file"
if ! flock --exclusive --wait 300 9; then
  printf 'Timed out waiting for the production deployment lock\n' >&2
  exit 3
fi

export KANOON_IMAGE
export KANOON_APP_ENV_FILE="$app_env"
compose=(docker compose --project-name kanoon-production --env-file "$compose_env" --file "$compose_file")

previous_release=""
previous_image=""
if [[ -L "$current_link" ]]; then
  previous_release="$(readlink --canonicalize "$current_link")"
  if [[ "$previous_release" != "$releases_root/"* ]]; then
    printf 'Current release link resolves outside the release root\n' >&2
    exit 2
  fi
  if [[ -f "$previous_release/release.env" ]]; then
    previous_image="$(sed -n 's/^KANOON_IMAGE=//p' "$previous_release/release.env")"
  fi
fi

deployment_started=0
rollback_application() {
  exit_code=$?
  trap - ERR
  set +e
  if ((deployment_started == 1)) && [[ -n "$previous_release" ]] && \
    [[ -f "$previous_release/docker-compose.production.yml" ]] && \
    [[ "$KANOON_IMAGE" =~ ^(ghcr\.io/[a-z0-9._/-]+@sha256:[a-f0-9]{64}|kanoon-backend:sha-[a-f0-9]{40})$ ]]; then
    printf 'Deployment failed; restoring the previous application image. Database migrations remain forward-only.\n' >&2
    export KANOON_IMAGE="$previous_image"
    previous_compose=(
      docker compose
      --project-name kanoon-production
      --env-file "$compose_env"
      --file "$previous_release/docker-compose.production.yml"
    )
    "${previous_compose[@]}" up --detach --no-deps backend backend-control-plane site-build-worker
    for attempt in {1..30}; do
      if curl --fail --silent --show-error --max-time 5 "$HEALTH_URL" >/dev/null; then
        break
      fi
      sleep 2
    done
  elif ((deployment_started == 1)); then
    printf 'Deployment failed without a managed previous release; stopping failed application containers.\n' >&2
    "${compose[@]}" stop backend backend-control-plane site-build-worker
  fi
  exit "$exit_code"
}
trap rollback_application ERR

"${compose[@]}" config --quiet
# "${compose[@]}" pull

# actual_revision="$(
#   docker image inspect "$KANOON_IMAGE" \
#     --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}'
# )"
# if [[ "$actual_revision" != "$RELEASE_ID" ]]; then
#   printf 'Image revision label does not match the requested release\n' >&2
#   exit 4
# fi

deployment_started=1
"${compose[@]}" up --detach --remove-orphans

# for attempt in {1..30}; do
#   if curl --fail --silent --show-error --max-time 5 "$HEALTH_URL" >/dev/null; then
#     break
#   fi
#   if ((attempt == 30)); then
#     printf 'Production readiness check did not become healthy\n' >&2
#     false
#   fi
#   sleep 2
# done

docker run --rm \
  --volume "$release_path:/release:ro" \
  "$KANOON_IMAGE" \
  python /release/deploy/production/verify_openapi.py \
  --expected /release/openapi.json \
  --actual-url "$OPENAPI_URL"

printf 'KANOON_IMAGE=%s\nRELEASE_ID=%s\n' "$KANOON_IMAGE" "$RELEASE_ID" > "$release_path/release.env"
chmod 640 "$release_path/release.env"

if [[ -n "$previous_release" && "$previous_release" != "$release_path" ]]; then
  temporary_previous="$previous_link.tmp.$$"
  ln --symbolic "$previous_release" "$temporary_previous"
  mv --force --no-target-directory "$temporary_previous" "$previous_link"
fi
temporary_current="$current_link.tmp.$$"
ln --symbolic "$release_path" "$temporary_current"
mv --force --no-target-directory "$temporary_current" "$current_link"

mapfile -t release_directories < <(
  find "$releases_root" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' \
    | sort --numeric-sort --reverse \
    | cut --delimiter=' ' --fields=2-
)
for ((index = KEEP_RELEASES; index < ${#release_directories[@]}; index++)); do
  candidate="${release_directories[$index]}"
  if [[ "$candidate" == "$release_path" || "$candidate" == "$previous_release" ]]; then
    continue
  fi
  [[ "$candidate" == "$releases_root/"* ]]
  rm --recursive --force --one-file-system -- "$candidate"
done

trap - ERR
printf 'Deployment succeeded: revision=%s image=%s\n' "$RELEASE_ID" "$KANOON_IMAGE"
