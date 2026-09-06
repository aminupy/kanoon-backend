from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = (ROOT / "docker-compose.production.yml").read_text(encoding="utf-8")


def service_block(name: str, next_name: str | None = None) -> str:
    block = COMPOSE.split(f"  {name}:\n", maxsplit=1)[1]
    if next_name is not None:
        block = block.split(f"  {next_name}:\n", maxsplit=1)[0]
    return block


def test_production_postgres_18_is_internal_and_uses_the_18_volume_layout() -> None:
    postgres = service_block("postgres", "migrate")

    image_line = next(
        line.strip() for line in postgres.splitlines() if line.strip().startswith("image:")
    )
    assert image_line.startswith("image: postgres:18-alpine@sha256:")
    assert len(image_line.rsplit(":", maxsplit=1)[1]) == 64
    assert "postgres-18-data:/var/lib/postgresql" in postgres
    assert "/var/lib/postgresql/data" not in postgres
    assert "00-kanoon-roles.sh:/docker-entrypoint-initdb.d/00-kanoon-roles.sh:ro" in postgres
    assert "POSTGRES_INITDB_ARGS: --data-checksums --auth-host=scram-sha-256" in postgres
    assert "ports:" not in postgres
    assert "- database" in postgres


def test_production_migrations_use_a_separate_owner_dsn_and_gate_services() -> None:
    migrate = service_block("migrate", "backend")
    backend = service_block("backend", "backend-control-plane")
    control = service_block("backend-control-plane", "site-build-worker")

    assert "alembic" in migrate and "upgrade" in migrate and "head" in migrate
    assert "KANOON_MIGRATION_DATABASE_DSN" in migrate
    assert "condition: service_healthy" in migrate
    assert "condition: service_completed_successfully" in backend
    assert "condition: service_completed_successfully" in control


def test_production_http_surfaces_are_loopback_only_and_database_isolated() -> None:
    backend = service_block("backend", "backend-control-plane")
    control = service_block("backend-control-plane", "site-build-worker")

    assert "ports:" not in backend
    assert "- edge" in backend
    assert "127.0.0.1:${KANOON_CONTROL_PLANE_PORT:-8001}:8001" in control
    assert "database:\n    internal: true" in COMPOSE
    assert "edge:\n    name: gateway\n    external: true" in COMPOSE
    assert "read_only: true" in COMPOSE
    assert "no-new-privileges:true" in COMPOSE


def test_production_environment_files_are_separated_and_ignored() -> None:
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    app_example = (ROOT / "deploy/production/app.env.example").read_text(encoding="utf-8")
    compose_example = (ROOT / "deploy/production/compose.env.example").read_text(encoding="utf-8")

    assert ".env.production\n" in ignore
    assert ".env.production.app\n" in ignore
    assert "KANOON_MIGRATION_DATABASE_DSN" not in app_example
    assert "POSTGRES_PASSWORD" not in app_example
    assert "KANOON_DATABASE_DSN" in app_example
    assert "KANOON_MIGRATION_DATABASE_DSN" in compose_example
    assert "KANOON_IMAGE=" in compose_example


def test_postgres_initializer_guards_role_separation_and_password_strength() -> None:
    initializer = (ROOT / "deploy/postgres/init/00-kanoon-roles.sh").read_text(encoding="utf-8")

    assert 'KANOON_DB_APP_USER" = "kanoon_app' in initializer
    assert 'KANOON_DB_APP_USER" = "$POSTGRES_USER' in initializer
    assert "${#KANOON_DB_APP_PASSWORD}" in initializer
    assert 'KANOON_DB_APP_PASSWORD" = "$POSTGRES_PASSWORD' in initializer
