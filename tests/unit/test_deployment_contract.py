from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_compose_publishes_control_plane_only_on_host_loopback() -> None:
    compose = (REPOSITORY_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    control_plane = compose.split("  backend-control-plane:\n", maxsplit=1)[1].split(
        "\nvolumes:", maxsplit=1
    )[0]

    assert '      - "127.0.0.1:8001:8001"' in control_plane
    assert '      - "8001:8001"' not in control_plane
    assert 'traefik.enable: "false"' in control_plane


def test_compose_separates_internal_and_browser_s3_endpoints() -> None:
    compose = (REPOSITORY_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    backend = compose.split("  backend:\n", maxsplit=1)[1].split(
        "\n  backend-control-plane:", maxsplit=1
    )[0]

    assert "${KANOON_S3_ENDPOINT_URL:?set the internal SeaweedFS S3 URL}" in backend
    assert ("${KANOON_S3_PUBLIC_ENDPOINT_URL:?set the public SeaweedFS S3 URL}") in backend
    assert "\n  minio:" not in compose
    assert "kanoon-minio" not in compose
