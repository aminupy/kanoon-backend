from __future__ import annotations

from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from fastapi import Request, Response
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import Settings
from app.core.database import Database
from app.tenancy.context import TenantContext, normalize_hostname
from app.tenancy.models import TenantDomain

RequestHandler = Callable[[Request], Awaitable[Response]]


class DynamicCORSMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, database: Database, settings: Settings) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.database = database
        self.settings = settings

    async def _origin_allowed(self, request: Request, origin: str) -> bool:
        if origin in self.settings.allowed_cors_origins:
            return True
        tenant = getattr(request.state, "tenant", None)
        if not isinstance(tenant, TenantContext):
            return False
        parsed = urlsplit(origin)
        if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
            return False
        try:
            hostname = normalize_hostname(parsed.hostname)
        except ValueError:
            return False
        async with self.database.global_session() as session:
            owner = await session.scalar(
                select(TenantDomain.tenant_id).where(
                    TenantDomain.hostname == hostname,
                    TenantDomain.is_active.is_(True),
                )
            )
        return owner == tenant.tenant_id

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        origin = request.headers.get("origin")
        if origin is None:
            return await call_next(request)
        allowed = await self._origin_allowed(request, origin)
        if request.method == "OPTIONS" and request.headers.get("access-control-request-method"):
            response = Response(status_code=204 if allowed else 403)
        else:
            response = await call_next(request)
        if allowed:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = (
                "Authorization,Content-Type,Idempotency-Key,X-Request-ID"
            )
            response.headers["Access-Control-Max-Age"] = "600"
            response.headers.append("Vary", "Origin")
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        return response
