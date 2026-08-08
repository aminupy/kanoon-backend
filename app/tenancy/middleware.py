from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import Settings
from app.core.database import Database
from app.core.errors import ApplicationError
from app.tenancy.context import request_hostname
from app.tenancy.models import TenantStatus
from app.tenancy.repository import TenantRepository

RequestHandler = Callable[[Request], Awaitable[Response]]


class TenantResolutionMiddleware(BaseHTTPMiddleware):
    EXEMPT_PATHS = frozenset({"/health/live", "/health/ready", "/docs", "/openapi.json"})
    EXEMPT_PREFIXES = (
        "/api/v1/public/payments/callback/",
        "/api/v1/internal/site-builds/",
    )

    def __init__(self, app: object, database: Database, settings: Settings) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.database = database
        self.settings = settings
        self.repository = TenantRepository()

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        path = request.url.path
        if path in self.EXEMPT_PATHS or any(path.startswith(p) for p in self.EXEMPT_PREFIXES):
            return await call_next(request)

        hostname = request_hostname(request, self.settings)
        async with self.database.global_session() as session:
            tenant = await self.repository.resolve_active_domain(session, hostname)
        if tenant is None:
            raise ApplicationError(
                "TENANT_NOT_FOUND", "The requested site is unavailable.", status_code=404
            )
        if tenant.status is not TenantStatus.ACTIVE:
            raise ApplicationError(
                "TENANT_UNAVAILABLE", "The requested site is unavailable.", status_code=404
            )
        request.state.tenant = tenant
        return await call_next(request)
