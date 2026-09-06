from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = ROOT / "deploy/production/deploy.sh"
ROLLBACK_SCRIPT = ROOT / "deploy/production/rollback.sh"


def _fake_runtime(tmp_path: Path) -> tuple[Path, Path]:
    binary_directory = tmp_path / "bin"
    binary_directory.mkdir()
    log_path = tmp_path / "docker.log"
    docker = binary_directory / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        'printf \'%s\\n\' "$*" >> "$FAKE_DOCKER_LOG"\n'
        'if [ "$1" = image ] && [ "$2" = inspect ]; then\n'
        "  printf '%s\\n' \"$FAKE_IMAGE_REVISION\"\n"
        "fi\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    curl = binary_directory / "curl"
    curl.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    curl.chmod(0o755)
    return binary_directory, log_path


def _release(root: Path, revision: str, image_character: str) -> Path:
    release = root / "releases" / revision
    release.mkdir(parents=True)
    (release / "docker-compose.production.yml").write_text("services: {}\n", encoding="utf-8")
    (release / "openapi.json").write_text("{}\n", encoding="utf-8")
    (release / "release.env").write_text(
        f"KANOON_IMAGE=ghcr.io/aminupy/kanoon-backend@sha256:{image_character * 64}\n"
        f"RELEASE_ID={revision}\n",
        encoding="utf-8",
    )
    return release


def _shared_environment(root: Path) -> None:
    shared = root / "shared"
    shared.mkdir(parents=True)
    for name in (".env.production", ".env.production.app"):
        path = shared / name
        path.write_text("TEST_ONLY=true\n", encoding="utf-8")
        path.chmod(0o600)


def _environment(
    root: Path,
    binary_directory: Path,
    log_path: Path,
    revision: str,
    image_character: str,
) -> dict[str, str]:
    return {
        **os.environ,
        "PATH": f"{binary_directory}:{os.environ['PATH']}",
        "DEPLOY_ROOT": str(root),
        "RELEASE_ID": revision,
        "KANOON_IMAGE": (f"ghcr.io/aminupy/kanoon-backend@sha256:{image_character * 64}"),
        "HEALTH_URL": "https://kanoon.example.test/health/ready",
        "OPENAPI_URL": "https://kanoon.example.test/openapi.json",
        "KEEP_RELEASES": "2",
        "FAKE_DOCKER_LOG": str(log_path),
        "FAKE_IMAGE_REVISION": revision,
    }


def test_deploy_marks_release_current_only_after_all_gates(tmp_path: Path) -> None:
    root = tmp_path / "kanoon"
    revision = "a" * 40
    release = _release(root, revision, "1")
    (release / "release.env").unlink()
    _shared_environment(root)
    binary_directory, log_path = _fake_runtime(tmp_path)

    completed = subprocess.run(  # noqa: S603
        [str(DEPLOY_SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
        env=_environment(root, binary_directory, log_path, revision, "1"),
    )

    assert completed.returncode == 0, completed.stderr
    assert (root / "current").resolve() == release
    assert f"RELEASE_ID={revision}" in (release / "release.env").read_text(encoding="utf-8")
    commands = log_path.read_text(encoding="utf-8")
    assert "compose --project-name kanoon-production" in commands
    assert "up --detach --remove-orphans" in commands
    assert "python /release/deploy/production/verify_openapi.py" in commands


def test_manual_rollback_swaps_release_links_without_migrating(tmp_path: Path) -> None:
    root = tmp_path / "kanoon"
    current_revision = "a" * 40
    previous_revision = "b" * 40
    current = _release(root, current_revision, "1")
    previous = _release(root, previous_revision, "2")
    _shared_environment(root)
    (root / "current").symlink_to(current)
    (root / "previous").symlink_to(previous)
    binary_directory, log_path = _fake_runtime(tmp_path)
    environment = _environment(root, binary_directory, log_path, previous_revision, "2")

    completed = subprocess.run(  # noqa: S603
        [str(ROLLBACK_SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert completed.returncode == 0, completed.stderr
    assert (root / "current").resolve() == previous
    assert (root / "previous").resolve() == current
    commands = log_path.read_text(encoding="utf-8")
    assert "up --detach --no-deps backend backend-control-plane site-build-worker" in commands
    assert "alembic" not in commands
