from __future__ import annotations

from fastapi import FastAPI

from app.application import create_base_app, install_common_middleware
from app.auth.router import platform_auth_router
from app.core.config import Settings, get_settings
from app.tenancy.platform_router import router as platform_tenants_router


def create_control_plane_app(settings: Settings | None = None) -> FastAPI:
    configured = settings or get_settings()
    application, _ = create_base_app(
        configured,
        title="Kanoon Control Plane API",
        description="Loopback-only authenticated platform administration API.",
        docs_url="/docs",
    )
    install_common_middleware(application)
    application.include_router(platform_auth_router)
    application.include_router(platform_tenants_router)
    return application


app = create_control_plane_app()
