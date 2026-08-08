from __future__ import annotations

from fastapi import Request

from app.core.config import Settings
from app.tenancy.context import normalize_hostname, request_hostname


def request_with_headers(*, host: str, forwarded: str | None, client: str) -> Request:
    headers = [(b"host", host.encode())]
    if forwarded:
        headers.append((b"x-forwarded-host", forwarded.encode()))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": headers,
            "client": (client, 1234),
            "server": ("localhost", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )


def test_hostname_normalization() -> None:
    assert normalize_hostname("School.Example.IR.:443") == "school.example.ir"
    assert normalize_hostname("مثال.ایران") == "xn--mgbh0fb.xn--mgba3a4f16a"


def test_forwarded_host_is_ignored_by_default() -> None:
    request = request_with_headers(
        host="school.example.ir", forwarded="evil.example", client="127.0.0.1"
    )
    assert request_hostname(request, Settings(environment="testing")) == "school.example.ir"


def test_forwarded_host_requires_a_trusted_peer() -> None:
    settings = Settings(
        environment="testing",
        trust_forwarded_host=True,
        trusted_proxy_cidrs=["10.0.0.0/8"],
    )
    untrusted = request_with_headers(
        host="school.example.ir", forwarded="forwarded.example", client="192.0.2.1"
    )
    trusted = request_with_headers(
        host="gateway.internal", forwarded="forwarded.example", client="10.1.2.3"
    )
    assert request_hostname(untrusted, settings) == "school.example.ir"
    assert request_hostname(trusted, settings) == "forwarded.example"
