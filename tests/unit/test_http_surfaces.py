from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import httpx
from fastapi import FastAPI

from app.control_plane import app as control_plane_app
from app.core.errors import ErrorBoundaryMiddleware
from app.core.http_security import DynamicCORSMiddleware, SecurityHeadersMiddleware
from app.core.logging import RequestLoggingMiddleware
from app.main import app as data_plane_app
from app.tenancy.middleware import TenantResolutionMiddleware


def _registered_paths(application: FastAPI) -> set[str]:
    def walk(routes: Iterable[Any]) -> set[str]:
        result: set[str] = set()
        for route in routes:
            path = getattr(route, "path", None)
            if isinstance(path, str):
                result.add(path)
            original_router = getattr(route, "original_router", None)
            if original_router is not None:
                result.update(walk(original_router.routes))
        return result

    return walk(application.routes)


def test_data_plane_route_table_contains_no_platform_route() -> None:
    paths = _registered_paths(data_plane_app)
    assert not any(path.startswith("/api/v1/platform") for path in paths)
    assert "/api/v1/admin/auth/login" in paths
    assert "/api/v1/public/site" in paths


def test_data_plane_openapi_contains_no_platform_path() -> None:
    paths = set(data_plane_app.openapi()["paths"])
    assert not any(path.startswith("/api/v1/platform") for path in paths)


def test_control_plane_route_and_openapi_are_platform_only() -> None:
    route_paths = _registered_paths(control_plane_app)
    schema = control_plane_app.openapi()
    schema_paths = set(schema["paths"])
    expected = {
        "/api/v1/platform/auth/login",
        "/api/v1/platform/auth/refresh",
        "/api/v1/platform/tenants",
        "/api/v1/platform/tenants/{tenant_id}/site-build-config",
    }
    assert expected <= route_paths
    assert expected <= schema_paths
    assert not any(path.startswith("/api/v1/admin") for path in schema_paths)
    assert not any(path.startswith("/api/v1/public") for path in schema_paths)
    assert not any(path.startswith("/api/v1/internal") for path in schema_paths)
    assert schema["info"]["title"] == "Kanoon Control Plane API"


def test_control_plane_does_not_inherit_tenant_resolution_or_cors() -> None:
    control_middleware = {
        str(getattr(item.cls, "__name__", item.cls)) for item in control_plane_app.user_middleware
    }
    data_middleware = {
        str(getattr(item.cls, "__name__", item.cls)) for item in data_plane_app.user_middleware
    }
    assert TenantResolutionMiddleware.__name__ in data_middleware
    assert DynamicCORSMiddleware.__name__ in data_middleware
    assert TenantResolutionMiddleware.__name__ not in control_middleware
    assert DynamicCORSMiddleware.__name__ not in control_middleware
    assert {
        RequestLoggingMiddleware.__name__,
        SecurityHeadersMiddleware.__name__,
        ErrorBoundaryMiddleware.__name__,
    } <= control_middleware


async def test_control_plane_routes_exist_and_non_platform_routes_do_not() -> None:
    transport = httpx.ASGITransport(app=control_plane_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://control") as client:
        login = await client.post("/api/v1/platform/auth/login", json={})
        tenants = await client.get("/api/v1/platform/tenants")
        data_route = await client.post("/api/v1/admin/auth/login", json={})
        live = await client.get("/health/live", headers={"Origin": "https://example.com"})
        docs = await client.get("/docs")
    assert login.status_code == 422
    assert tenants.status_code == 401
    assert data_route.status_code == 404
    assert live.status_code == 200
    assert "access-control-allow-origin" not in live.headers
    assert docs.status_code == 200
