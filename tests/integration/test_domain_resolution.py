from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.main import create_app
from app.tenancy.models import Tenant, TenantDomain

pytestmark = pytest.mark.integration


@pytest.fixture
async def domains(owner_engine: AsyncEngine) -> dict[str, str]:
    active_id, suspended_id = uuid.uuid4(), uuid.uuid4()
    active_host = f"active-{active_id}.example.test"
    inactive_host = f"inactive-{active_id}.example.test"
    suspended_host = f"suspended-{suspended_id}.example.test"
    async with owner_engine.begin() as connection:
        await connection.execute(
            insert(Tenant),
            [
                {
                    "id": active_id,
                    "name": "Active",
                    "slug": f"active-{active_id}",
                    "status": "ACTIVE",
                    "default_locale": "fa-IR",
                    "timezone": "Asia/Tehran",
                    "default_currency": "IRR",
                },
                {
                    "id": suspended_id,
                    "name": "Suspended",
                    "slug": f"suspended-{suspended_id}",
                    "status": "SUSPENDED",
                    "default_locale": "fa-IR",
                    "timezone": "Asia/Tehran",
                    "default_currency": "IRR",
                },
            ],
        )
        await connection.execute(
            insert(TenantDomain),
            [
                {
                    "tenant_id": active_id,
                    "hostname": active_host,
                    "is_primary": True,
                    "is_active": True,
                    "created_at": datetime.now(UTC),
                },
                {
                    "tenant_id": active_id,
                    "hostname": inactive_host,
                    "is_primary": False,
                    "is_active": False,
                    "created_at": datetime.now(UTC),
                },
                {
                    "tenant_id": suspended_id,
                    "hostname": suspended_host,
                    "is_primary": True,
                    "is_active": True,
                    "created_at": datetime.now(UTC),
                },
            ],
        )
    return {"active": active_host, "inactive": inactive_host, "suspended": suspended_host}


async def get(app: object, host: str, **headers: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/api/v1/public/site", headers={"Host": host, **headers})


async def test_known_unknown_inactive_and_suspended_domains(
    settings: Settings, domains: dict[str, str]
) -> None:
    app = create_app(settings)
    known = await get(app, domains["active"])
    unknown = await get(app, "unknown.example.test")
    inactive = await get(app, domains["inactive"])
    suspended = await get(app, domains["suspended"])
    assert known.status_code == 200
    assert unknown.status_code == inactive.status_code == suspended.status_code == 404
    assert unknown.json()["code"] == "TENANT_NOT_FOUND"
    assert suspended.json()["code"] == "TENANT_UNAVAILABLE"
    await app.state.database.dispose()


async def test_spoofed_forwarded_host_is_ignored(
    settings: Settings, domains: dict[str, str]
) -> None:
    app = create_app(settings)
    response = await get(
        app,
        domains["active"],
        **{"X-Forwarded-Host": "unknown.example.test"},
    )
    assert response.status_code == 200
    await app.state.database.dispose()


async def test_forwarded_host_is_used_only_from_an_explicitly_trusted_hop(
    settings: Settings, domains: dict[str, str]
) -> None:
    untrusted_settings = settings.model_copy(
        update={"trust_forwarded_host": True, "trusted_proxy_cidrs": ["192.0.2.0/24"]}
    )
    untrusted_app = create_app(untrusted_settings)
    untrusted = await get(
        untrusted_app,
        domains["active"],
        **{"X-Forwarded-Host": "unknown.example.test"},
    )
    assert untrusted.status_code == 200
    await untrusted_app.state.database.dispose()

    trusted_settings = settings.model_copy(
        update={"trust_forwarded_host": True, "trusted_proxy_cidrs": ["127.0.0.1/32"]}
    )
    trusted_app = create_app(trusted_settings)
    trusted = await get(
        trusted_app,
        "unknown.example.test",
        **{"X-Forwarded-Host": domains["active"]},
    )
    assert trusted.status_code == 200
    await trusted_app.state.database.dispose()
