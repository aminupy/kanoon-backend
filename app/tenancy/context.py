from __future__ import annotations

import ipaddress
import uuid
from dataclasses import dataclass

from fastapi import Request

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.tenancy.models import TenantStatus


@dataclass(frozen=True, slots=True)
class TenantContext:
    tenant_id: uuid.UUID
    slug: str
    hostname: str
    status: TenantStatus
    default_locale: str
    timezone: str
    default_currency: str


def normalize_hostname(raw_host: str) -> str:
    value = raw_host.strip()
    if not value:
        raise ValueError("hostname is empty")
    if value.startswith("["):
        closing = value.find("]")
        if closing < 0:
            raise ValueError("invalid IPv6 hostname")
        host = value[1:closing]
    else:
        host = value.rsplit(":", 1)[0] if value.count(":") == 1 else value
    host = host.rstrip(".").lower()
    if not host or len(host) > 253:
        raise ValueError("invalid hostname length")
    try:
        normalized = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("invalid internationalized hostname") from exc
    labels = normalized.split(".")
    if any(not label or len(label) > 63 for label in labels):
        raise ValueError("invalid hostname label")
    return normalized


def _client_is_trusted_proxy(request: Request, settings: Settings) -> bool:
    if not settings.trust_forwarded_host or request.client is None:
        return False
    try:
        client_ip = ipaddress.ip_address(request.client.host)
    except ValueError:
        return False
    return any(client_ip in ipaddress.ip_network(cidr) for cidr in settings.trusted_proxy_cidrs)


def request_hostname(request: Request, settings: Settings) -> str:
    raw_host = request.headers.get("host", "")
    if _client_is_trusted_proxy(request, settings):
        forwarded_host = request.headers.get("x-forwarded-host")
        if forwarded_host:
            # The nearest trusted proxy is expected to replace, not append, this header.
            raw_host = forwarded_host.split(",", 1)[0].strip()
    try:
        return normalize_hostname(raw_host)
    except ValueError as exc:
        raise ApplicationError(
            "TENANT_NOT_FOUND", "The requested site is unavailable.", status_code=404
        ) from exc


def tenant_context_from_request(request: Request) -> TenantContext:
    context = getattr(request.state, "tenant", None)
    if not isinstance(context, TenantContext):
        raise ApplicationError(
            "TENANT_CONTEXT_REQUIRED", "The requested site is unavailable.", status_code=404
        )
    return context
