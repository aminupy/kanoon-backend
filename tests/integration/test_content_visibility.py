from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from app.content.models import Banner, Post
from app.core.config import Settings
from app.main import create_app
from app.media.models import MediaAsset
from app.tenancy.models import Tenant, TenantDomain, TenantFeature

pytestmark = pytest.mark.integration


@pytest.fixture
async def content_host(owner_engine: AsyncEngine) -> str:
    tenant_id, media_id = uuid.uuid4(), uuid.uuid4()
    hostname = f"content-{tenant_id}.example.test"
    now = datetime.now(UTC)
    async with owner_engine.begin() as connection:
        await connection.execute(
            insert(Tenant),
            {
                "id": tenant_id,
                "name": "Content Tenant",
                "slug": f"content-{tenant_id}",
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
            insert(TenantFeature),
            [
                {
                    "tenant_id": tenant_id,
                    "feature_key": "banners",
                    "enabled": True,
                    "configuration": {},
                },
                {
                    "tenant_id": tenant_id,
                    "feature_key": "news",
                    "enabled": True,
                    "configuration": {},
                },
            ],
        )
        await connection.execute(
            insert(MediaAsset),
            {
                "id": media_id,
                "tenant_id": tenant_id,
                "object_key": f"tenants/{tenant_id}/banner.jpg",
                "original_filename": "banner.jpg",
                "mime_type": "image/jpeg",
                "size_bytes": 100,
                "status": "READY",
                "visibility": "PUBLIC",
            },
        )
        await connection.execute(
            insert(Banner),
            [
                {
                    "tenant_id": tenant_id,
                    "title": "Visible",
                    "image_id": media_id,
                    "sort_order": 0,
                    "status": "PUBLISHED",
                    "starts_at": now - timedelta(minutes=1),
                    "ends_at": now + timedelta(minutes=5),
                },
                {
                    "tenant_id": tenant_id,
                    "title": "Future",
                    "image_id": media_id,
                    "sort_order": 1,
                    "status": "PUBLISHED",
                    "starts_at": now + timedelta(days=1),
                    "ends_at": None,
                },
                {
                    "tenant_id": tenant_id,
                    "title": "Draft",
                    "image_id": media_id,
                    "sort_order": 2,
                    "status": "DRAFT",
                    "starts_at": None,
                    "ends_at": None,
                },
            ],
        )
        await connection.execute(
            insert(Post),
            [
                {
                    "tenant_id": tenant_id,
                    "kind": "NEWS",
                    "title": "Published",
                    "slug": "published",
                    "body": "body",
                    "status": "PUBLISHED",
                    "published_at": now - timedelta(minutes=1),
                },
                {
                    "tenant_id": tenant_id,
                    "kind": "NEWS",
                    "title": "Draft",
                    "slug": "draft",
                    "body": "body",
                    "status": "DRAFT",
                    "published_at": None,
                },
            ],
        )
    return hostname


async def test_only_currently_visible_content_is_public(
    settings: Settings, content_host: str
) -> None:
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        banner_response = await client.get("/api/v1/public/banners", headers={"Host": content_host})
        news_response = await client.get("/api/v1/public/news", headers={"Host": content_host})
    assert banner_response.status_code == 200
    assert [item["title"] for item in banner_response.json()] == ["Visible"]
    assert news_response.status_code == 200
    assert [item["title"] for item in news_response.json()["items"]] == ["Published"]
    await app.state.database.dispose()
