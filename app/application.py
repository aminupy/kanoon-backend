from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.core.config import Settings
from app.core.database import Database
from app.core.errors import ApplicationError, ErrorBoundaryMiddleware, install_error_handlers
from app.core.http_security import SecurityHeadersMiddleware
from app.core.logging import RequestLoggingMiddleware, configure_logging

AsyncCheck = Callable[[], Awaitable[None]]


def create_base_app(
    settings: Settings,
    *,
    title: str,
    description: str,
    docs_url: str | None,
    startup_checks: Sequence[AsyncCheck] = (),
    readiness_checks: Sequence[AsyncCheck] = (),
) -> tuple[FastAPI, Database]:
    """Create shared application infrastructure without choosing an HTTP surface."""

    configure_logging(debug=settings.debug)
    database = Database(settings)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        del application
        try:
            for check in startup_checks:
                await check()
            yield
        finally:
            await database.dispose()

    application = FastAPI(
        title=title,
        version="1.0.0",
        description=description,
        lifespan=lifespan,
        docs_url=docs_url,
        redoc_url=None,
    )
    application.state.database = database
    application.state.settings = settings
    install_error_handlers(application)
    install_health_routes(application, database, readiness_checks=readiness_checks)
    return application, database


def install_common_middleware(application: FastAPI) -> None:
    application.add_middleware(RequestLoggingMiddleware)
    application.add_middleware(SecurityHeadersMiddleware)
    application.add_middleware(ErrorBoundaryMiddleware)


def install_health_routes(
    application: FastAPI,
    database: Database,
    *,
    readiness_checks: Sequence[AsyncCheck],
) -> None:
    @application.get("/health/live", tags=["health"])
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/health/ready", tags=["health"])
    async def ready() -> dict[str, str]:
        try:
            async with database.global_session() as session:
                await session.execute(text("SELECT 1"))
            for check in readiness_checks:
                await check()
        except Exception as exc:
            raise ApplicationError(
                "SERVICE_NOT_READY", "A required dependency is unavailable.", status_code=503
            ) from exc
        return {"status": "ok"}
