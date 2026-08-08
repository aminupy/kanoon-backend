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
