from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_ci_runs_complete_postgres_18_and_storage_gates() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()

    assert "push:" in workflow
    assert "pull_request:" in workflow
    assert "image: postgres:18-alpine" in workflow
    assert "KANOON_TEST_DATABASE_DSN:" in workflow
    assert "KANOON_TEST_S3_ENDPOINT_URL:" in workflow
    assert "uv run pytest -q" in workflow
    assert "uv run alembic downgrade -1" in workflow
    assert "verify_openapi.py" in workflow
    assert "name: Container build gate" in workflow
    assert "push: false" in workflow


def test_actions_are_commit_pinned_and_production_deploys_only_main_digest() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    actions = re.findall(r"uses:\s+([^\s#]+)", workflow)

    assert actions
    assert all(re.fullmatch(r"[^@]+@[a-f0-9]{40}", action) for action in actions)
    assert "github.event_name == 'push' && github.ref == 'refs/heads/main'" in workflow
    assert "image_ref=${IMAGE_NAME}@${IMAGE_DIGEST}" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "secrets.DEPLOY_SSH_PRIVATE_KEY" in workflow
    assert "secrets.DEPLOY_SSH_KNOWN_HOSTS" in workflow
    assert "secrets.GHCR_DEPLOY_TOKEN" in workflow


def test_host_deployment_is_locked_migration_gated_and_forward_only() -> None:
    script = (ROOT / "deploy/production/deploy.sh").read_text()

    assert "flock --exclusive" in script
    assert '"${compose[@]}" up --detach --remove-orphans' in script
    assert "verify_openapi.py" in script
    assert "Database migrations remain forward-only" in script
    assert "stopping failed application containers" in script
    assert "alembic downgrade" not in script
    assert 'mv --force --no-target-directory "$temporary_current" "$current_link"' in script

    rollback = (ROOT / "deploy/production/rollback.sh").read_text()
    assert "flock --exclusive" in rollback
    assert "--no-deps backend backend-control-plane site-build-worker" in rollback
    assert "verify_openapi.py" in rollback
    assert "alembic downgrade" not in rollback


def test_release_bundle_cannot_contain_host_environment_files() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    bundle = workflow.split('tar --create --gzip --file "$RUNNER_TEMP/kanoon-release.tgz"', 1)[1]
    bundle = bundle.split("scp ", 1)[0]

    assert ".env.production" not in bundle
    assert ".env.production.app" not in bundle
