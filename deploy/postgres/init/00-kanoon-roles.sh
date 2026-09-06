#!/bin/sh
set -eu

: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${KANOON_DB_APP_USER:?KANOON_DB_APP_USER is required}"
: "${KANOON_DB_APP_PASSWORD:?KANOON_DB_APP_PASSWORD is required}"

case "$KANOON_DB_APP_USER" in
  *[!a-zA-Z0-9_]* | [0-9]* | "")
    echo "KANOON_DB_APP_USER must be a valid unquoted PostgreSQL role name" >&2
    exit 1
    ;;
esac

if [ "$KANOON_DB_APP_USER" = "kanoon_app" ] || [ "$KANOON_DB_APP_USER" = "$POSTGRES_USER" ]; then
  echo "KANOON_DB_APP_USER must differ from kanoon_app and the migration owner" >&2
  exit 1
fi

if [ "${#KANOON_DB_APP_PASSWORD}" -lt 24 ]; then
  echo "KANOON_DB_APP_PASSWORD must contain at least 24 characters" >&2
  exit 1
fi

if [ "$KANOON_DB_APP_PASSWORD" = "$POSTGRES_PASSWORD" ]; then
  echo "runtime and migration-owner database passwords must differ" >&2
  exit 1
fi

# This script runs only when the PostgreSQL data directory is first initialized.
# Values are passed as psql variables so passwords never become SQL source or log output.
psql \
  --set=ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set=app_user="$KANOON_DB_APP_USER" \
  --set=app_password="$KANOON_DB_APP_PASSWORD" <<'SQL'
DO $roles$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'kanoon_app') THEN
        CREATE ROLE kanoon_app
            NOLOGIN
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE
            NOINHERIT
            NOBYPASSRLS;
    END IF;
END
$roles$;

SELECT format(
    'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT NOBYPASSRLS PASSWORD %L',
    :'app_user',
    :'app_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user')
\gexec

SELECT format(
    'ALTER ROLE %I WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT NOBYPASSRLS PASSWORD %L',
    :'app_user',
    :'app_password'
)
\gexec

GRANT kanoon_app TO :"app_user";
SQL
