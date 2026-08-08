from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from app.auth.models import TenantMembership, User
from app.auth.security import create_access_token, hash_password
from app.control_plane import create_control_plane_app
from app.core.config import Settings
from app.main import create_app
from app.tenancy.models import Tenant, TenantDomain, TenantFeature

pytestmark = pytest.mark.integration


@pytest.fixture
async def surface_identities(owner_engine: AsyncEngine) -> dict[str, object]:
    tenant_id = uuid.uuid4()
    tenant_admin_id = uuid.uuid4()
    platform_admin_id = uuid.uuid4()
    hostname = f"surface-{tenant_id}.example.test"
    tenant_email = f"tenant-{tenant_admin_id}@example.com"
    platform_email = f"platform-{platform_admin_id}@example.com"
    tenant_password = "tenant-test-password-123"
    platform_password = "platform-test-password-123"
    now = datetime.now(UTC)
    async with owner_engine.begin() as connection:
        await connection.execute(
            insert(Tenant),
            {
                "id": tenant_id,
                "name": "Surface Tenant",
                "slug": f"surface-{tenant_id}",
                "status": "ACTIVE",
                "default_locale": "fa-IR",
                "timezone": "Asia/Tehran",
                "default_currency": "IRR",
            },
        )
        await connection.execute(
            insert(TenantDomain),
            {
                "tenant_id": tenant_id,
                "hostname": hostname,
                "is_primary": True,
                "is_active": True,
                "created_at": now,
            },
        )
        await connection.execute(
            insert(User),
            [
                {
                    "id": tenant_admin_id,
                    "email": tenant_email,
                    "password_hash": hash_password(tenant_password),
                    "is_active": True,
                    "is_platform_admin": False,
                },
                {
                    "id": platform_admin_id,
                    "email": platform_email,
                    "password_hash": hash_password(platform_password),
                    "is_active": True,
                    "is_platform_admin": True,
                },
            ],
        )
        await connection.execute(
            insert(TenantMembership),
            {
                "tenant_id": tenant_id,
                "user_id": tenant_admin_id,
                "role": "TENANT_ADMIN",
                "created_at": now,
            },
        )
        await connection.execute(
            insert(TenantFeature),
            {
                "tenant_id": tenant_id,
                "feature_key": "blog",
                "enabled": True,
                "configuration": {},
            },
        )
    return {
        "tenant_id": tenant_id,
        "tenant_admin_id": tenant_admin_id,
        "platform_admin_id": platform_admin_id,
        "hostname": hostname,
        "tenant_email": tenant_email,
        "platform_email": platform_email,
        "tenant_password": tenant_password,
        "platform_password": platform_password,
    }


async def test_surface_routing_and_authentication_isolation(
    settings: Settings, surface_identities: dict[str, object]
) -> None:
    tenant_id = surface_identities["tenant_id"]
    tenant_admin_id = surface_identities["tenant_admin_id"]
    platform_admin_id = surface_identities["platform_admin_id"]
    hostname = surface_identities["hostname"]
    assert isinstance(tenant_id, uuid.UUID)
    assert isinstance(tenant_admin_id, uuid.UUID)
    assert isinstance(platform_admin_id, uuid.UUID)
    assert isinstance(hostname, str)
    tenant_token, _ = create_access_token(
        settings,
        user_id=tenant_admin_id,
        tenant_id=tenant_id,
        is_platform_admin=False,
    )
    platform_token, _ = create_access_token(
        settings,
        user_id=platform_admin_id,
        tenant_id=None,
        is_platform_admin=True,
    )
    data_app = create_app(settings)
    control_app = create_control_plane_app(settings)
    data_transport = httpx.ASGITransport(app=data_app)
    control_transport = httpx.ASGITransport(app=control_app)
    async with (
        httpx.AsyncClient(transport=data_transport, base_url="http://data") as data_client,
        httpx.AsyncClient(transport=control_transport, base_url="http://control") as control_client,
    ):
        public_platform_login = await data_client.post(
            "/api/v1/platform/auth/login",
            headers={"Host": hostname},
            json={"email": "invalid@example.test", "password": "invalid"},
        )
        public_platform_tenants = await data_client.get(
            "/api/v1/platform/tenants",
            headers={"Host": hostname, "Authorization": f"Bearer {platform_token}"},
        )
        public_platform_tenants_without_auth = await data_client.get(
            "/api/v1/platform/tenants",
            headers={"Host": hostname},
        )
        tenant_data_access = await data_client.get(
            "/api/v1/admin/blog",
            headers={"Host": hostname, "Authorization": f"Bearer {tenant_token}"},
        )
        platform_token_on_data_plane = await data_client.get(
            "/api/v1/admin/blog",
            headers={"Host": hostname, "Authorization": f"Bearer {platform_token}"},
        )
        tenant_login = await data_client.post(
            "/api/v1/admin/auth/login",
            headers={"Host": hostname},
            json={
                "email": surface_identities["tenant_email"],
                "password": surface_identities["tenant_password"],
            },
        )

        control_missing_auth = await control_client.get("/api/v1/platform/tenants")
        tenant_token_on_control = await control_client.get(
            "/api/v1/platform/tenants",
            headers={"Authorization": f"Bearer {tenant_token}"},
        )
        platform_access = await control_client.get(
            "/api/v1/platform/tenants",
            headers={"Authorization": f"Bearer {platform_token}"},
        )
        tenant_platform_login = await control_client.post(
            "/api/v1/platform/auth/login",
            json={
                "email": surface_identities["tenant_email"],
                "password": surface_identities["tenant_password"],
            },
        )
        platform_login = await control_client.post(
            "/api/v1/platform/auth/login",
            json={
                "email": surface_identities["platform_email"],
                "password": surface_identities["platform_password"],
            },
        )
        control_ready = await control_client.get("/health/ready")

    assert public_platform_login.status_code == 404
    assert public_platform_tenants.status_code == 404
    assert public_platform_tenants_without_auth.status_code == 404
    assert tenant_data_access.status_code == 200
    assert platform_token_on_data_plane.status_code == 403
    assert tenant_login.status_code == 200, tenant_login.text
    assert control_missing_auth.status_code == 401
    assert tenant_token_on_control.status_code == 403
    assert platform_access.status_code == 200
    assert tenant_platform_login.status_code == 401, tenant_platform_login.text
    assert platform_login.status_code == 200, platform_login.text
    assert control_ready.status_code == 200
    await data_app.state.database.dispose()
    await control_app.state.database.dispose()
