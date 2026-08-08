from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.tenancy.context import TenantContext

RequestHandler = Callable[[Request], Awaitable[Response]]


def configure_logging(*, debug: bool) -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(10 if debug else 20),
        cache_logger_on_first_use=True,
    )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()
        response: Response | None = None
        try:
            response = await call_next(request)
            return response
        finally:
            tenant = getattr(request.state, "tenant", None)
            tenant_id = str(tenant.tenant_id) if isinstance(tenant, TenantContext) else None
            structlog.get_logger("http.request").info(
                "request_completed",
                request_id=request_id,
                tenant_id=tenant_id,
                method=request.method,
                route=request.url.path,
                status=response.status_code if response is not None else 500,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            if response is not None:
                response.headers["X-Request-ID"] = request_id
