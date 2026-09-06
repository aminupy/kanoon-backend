from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from app.auth.models import TenantMembership, User
from app.auth.security import create_access_token
from app.content.models import HonorCategory
from app.core.config import Settings
from app.exams.models import PricingPlan
from app.main import create_app
from app.media.models import MediaAsset
from app.tenancy.features import FEATURE_KEYS
from app.tenancy.models import Tenant, TenantDomain, TenantFeature

pytestmark = pytest.mark.integration


@pytest.fixture
async def admin_content_context(owner_engine: AsyncEngine, settings: Settings) -> dict[str, Any]:
    tenant_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    image_id = uuid.uuid4()
    pdf_id = uuid.uuid4()
    category_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    host = f"admin-update-{tenant_id}.example.test"
    now = datetime.now(UTC)
    async with owner_engine.begin() as connection:
        await connection.execute(
            insert(Tenant),
            {
                "id": tenant_id,
                "name": "Admin update tenant",
                "slug": f"admin-update-{tenant_id}",
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
                "hostname": host,
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
                    "feature_key": feature,
                    "enabled": True,
                    "configuration": {},
                }
                for feature in FEATURE_KEYS
            ],
        )
        await connection.execute(
            insert(User),
            {
                "id": admin_id,
                "email": f"admin-update-{admin_id}@example.test",
                "password_hash": "!",
                "is_active": True,
                "is_platform_admin": False,
            },
        )
        await connection.execute(
            insert(TenantMembership),
            {
                "tenant_id": tenant_id,
                "user_id": admin_id,
                "role": "TENANT_ADMIN",
                "created_at": now,
            },
        )
        await connection.execute(
            insert(MediaAsset),
            [
                {
                    "id": image_id,
                    "tenant_id": tenant_id,
                    "object_key": f"tenants/{tenant_id}/fixture.png",
                    "original_filename": "fixture.png",
                    "mime_type": "image/png",
                    "size_bytes": 68,
                    "status": "READY",
                    "visibility": "PUBLIC",
                },
                {
                    "id": pdf_id,
                    "tenant_id": tenant_id,
                    "object_key": f"tenants/{tenant_id}/fixture.pdf",
                    "original_filename": "fixture.pdf",
                    "mime_type": "application/pdf",
                    "size_bytes": 128,
                    "status": "READY",
                    "visibility": "PUBLIC",
                },
            ],
        )
        await connection.execute(
            insert(HonorCategory),
            {
                "id": category_id,
                "tenant_id": tenant_id,
                "name": "Existing category",
                "slug": f"existing-category-{category_id}",
                "sort_order": 0,
                "is_active": True,
            },
        )
        await connection.execute(
            insert(PricingPlan),
            {
                "id": plan_id,
                "tenant_id": tenant_id,
                "title": "Existing plan",
                "slug": f"existing-plan-{plan_id}",
                "description": "Existing plan",
                "mode": "ONLINE",
                "amount": 0,
                "currency": "IRR",
                "features": [],
                "sort_order": 0,
                "is_featured": False,
                "status": "PUBLISHED",
            },
        )
    token, _ = create_access_token(
        settings,
        user_id=admin_id,
        tenant_id=tenant_id,
        is_platform_admin=False,
    )
    return {
        "app": create_app(settings),
        "host": host,
        "headers": {"Host": host, "Authorization": f"Bearer {token}"},
        "public_headers": {"Host": host},
        "image_id": image_id,
        "pdf_id": pdf_id,
        "category_id": category_id,
        "plan_id": plan_id,
    }


def family_spec(family: str, context: dict[str, Any]) -> dict[str, Any]:
    suffix = uuid.uuid4().hex
    specs: dict[str, dict[str, Any]] = {
        "posts": {
            "collection": "/api/v1/admin/posts",
            "list_query": {"kind": "NEWS"},
            "create": {
                "kind": "NEWS",
                "title": "Initial news",
                "slug": f"news-{suffix}",
                "body": "Initial",
                "status": "DRAFT",
            },
            "update": {
                "kind": "NEWS",
                "title": "Updated news",
                "slug": f"news-{suffix}",
                "body": "Updated",
                "status": "PUBLISHED",
            },
            "public": "/api/v1/public/news",
            "public_items": lambda body: body["items"],
            "detail": lambda body: f"/api/v1/public/news/{body['slug']}",
            "related": {},
            "invalid_related": {"cover_image_id": str(uuid.uuid4())},
            "duplicate_slug": True,
        },
        "banners": {
            "collection": "/api/v1/admin/banners",
            "create": {
                "title": "Initial banner",
                "image_id": str(context["image_id"]),
                "status": "DRAFT",
            },
            "update": {
                "title": "Updated banner",
                "image_id": str(context["image_id"]),
                "status": "PUBLISHED",
            },
            "public": "/api/v1/public/banners",
            "public_items": lambda body: body,
            "related": {"image_id": str(context["image_id"])},
            "invalid_related": {"image_id": str(uuid.uuid4())},
        },
        "honor-categories": {
            "collection": "/api/v1/admin/honor-categories",
            "create": {
                "name": "Initial category",
                "slug": f"category-{suffix}",
                "is_active": False,
            },
            "update": {"name": "Updated category", "slug": f"category-{suffix}", "is_active": True},
            "public": None,
            "related": {},
            "duplicate_slug": True,
        },
        "honors": {
            "collection": "/api/v1/admin/honors",
            "create": {
                "category_id": str(context["category_id"]),
                "student_name": "Initial Student",
                "title": "Initial honor",
                "status": "DRAFT",
            },
            "update": {
                "category_id": str(context["category_id"]),
                "student_name": "Updated Student",
                "title": "Updated honor",
                "status": "PUBLISHED",
            },
            "public": "/api/v1/public/honors",
            "public_items": lambda body: body["items"],
            "related": {"category_id": str(context["category_id"])},
            "invalid_related": {"category_id": str(uuid.uuid4())},
        },
        "staff": {
            "collection": "/api/v1/admin/staff",
            "create": {
                "first_name": "Initial",
                "last_name": "Teacher",
                "display_name": "Initial Teacher",
                "member_type": "TEACHER",
                "title": "Teacher",
                "is_active": False,
            },
            "update": {
                "first_name": "Updated",
                "last_name": "Teacher",
                "display_name": "Updated Teacher",
                "member_type": "TEACHER",
                "title": "Senior Teacher",
                "image_id": str(context["image_id"]),
                "is_active": True,
            },
            "public": "/api/v1/public/staff",
            "public_items": lambda body: body,
            "related": {"image_id": str(context["image_id"])},
            "invalid_related": {"image_id": str(uuid.uuid4())},
        },
        "pricing-plans": {
            "collection": "/api/v1/admin/pricing-plans",
            "create": {
                "title": "Initial plan",
                "slug": f"plan-{suffix}",
                "description": "Initial",
                "mode": "ONLINE",
                "amount": 0,
                "currency": "IRR",
                "status": "DRAFT",
            },
            "update": {
                "title": "Updated plan",
                "slug": f"plan-{suffix}",
                "description": "Updated",
                "mode": "ONLINE",
                "amount": 1000,
                "currency": "IRR",
                "status": "PUBLISHED",
            },
            "public": "/api/v1/public/pricing-plans",
            "public_items": lambda body: body,
            "related": {},
            "duplicate_slug": True,
        },
        "exams": {
            "collection": "/api/v1/admin/exams",
            "create": {
                "title": "Initial exam",
                "slug": f"exam-{suffix}",
                "description": "Initial",
                "mode": "ONLINE",
                "status": "DRAFT",
                "pricing_plan_ids": [],
            },
            "update": {
                "title": "Updated exam",
                "slug": f"exam-{suffix}",
                "description": "Updated",
                "mode": "ONLINE",
                "status": "REGISTRATION_OPEN",
                "pricing_plan_ids": [str(context["plan_id"])],
            },
            "public": "/api/v1/public/exams",
            "public_items": lambda body: body,
            "related": {"pricing_plan_ids": [str(context["plan_id"])]},
            "invalid_related": {"pricing_plan_ids": [str(uuid.uuid4())]},
            "duplicate_slug": True,
        },
        "sample-exams": {
            "collection": "/api/v1/admin/sample-exams",
            "create": {
                "title": "Initial sample",
                "file_media_id": str(context["pdf_id"]),
                "status": "DRAFT",
            },
            "update": {
                "title": "Updated sample",
                "file_media_id": str(context["pdf_id"]),
                "cover_media_id": str(context["image_id"]),
                "status": "PUBLISHED",
            },
            "public": "/api/v1/public/sample-exams",
            "public_items": lambda body: body["items"],
            "related": {
                "file_media_id": str(context["pdf_id"]),
                "cover_media_id": str(context["image_id"]),
            },
            "invalid_related": {"file_media_id": str(uuid.uuid4())},
        },
        "gallery": {
            "collection": "/api/v1/admin/gallery",
            "create": {"title": "Initial gallery", "slug": f"gallery-{suffix}", "status": "DRAFT"},
            "update": {
                "title": "Updated gallery",
                "slug": f"gallery-{suffix}",
                "cover_image_id": str(context["image_id"]),
                "status": "PUBLISHED",
            },
            "public": "/api/v1/public/gallery",
            "public_items": lambda body: body["items"],
            "detail": lambda body: f"/api/v1/public/gallery/{body['slug']}",
            "related": {"cover_image_id": str(context["image_id"])},
            "invalid_related": {"cover_image_id": str(uuid.uuid4())},
            "duplicate_slug": True,
        },
    }
    return specs[family]


@pytest.mark.parametrize(
    "family",
    [
        "posts",
        "banners",
        "honor-categories",
        "honors",
        "staff",
        "pricing-plans",
        "exams",
        "sample-exams",
        "gallery",
    ],
)
async def test_admin_content_update_publish_archive_lifecycle(
    family: str, admin_content_context: dict[str, Any]
) -> None:
    context = admin_content_context
    spec = family_spec(family, context)
    transport = httpx.ASGITransport(app=context["app"])
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            spec["collection"], headers=context["headers"], json=spec["create"]
        )
        assert created.status_code == 201
        entity_id = created.json()["id"]
        created_updated_at = created.json()["updated_at"]

        malformed = await client.put(
            f"{spec['collection']}/not-a-uuid", headers=context["headers"], json=spec["update"]
        )
        assert malformed.status_code == 422
        nonexistent = await client.put(
            f"{spec['collection']}/{uuid.uuid4()}", headers=context["headers"], json=spec["update"]
        )
        assert nonexistent.status_code == 404
        invalid = await client.put(
            f"{spec['collection']}/{entity_id}",
            headers=context["headers"],
            json={**spec["update"], "status": "INVALID"}
            if "status" in spec["update"]
            else {**spec["update"], "sort_order": 100_001},
        )
        assert invalid.status_code == 422

        if invalid_related := spec.get("invalid_related"):
            bad_relationship = await client.put(
                f"{spec['collection']}/{entity_id}",
                headers=context["headers"],
                json={**spec["update"], **invalid_related},
            )
            assert bad_relationship.status_code in {409, 422}
            assert bad_relationship.json()["code"] != "INTERNAL_SERVER_ERROR"

        updated = await client.put(
            f"{spec['collection']}/{entity_id}", headers=context["headers"], json=spec["update"]
        )
        assert updated.status_code == 200, updated.json().get("code")
        body = updated.json()
        assert body["updated_at"] >= created_updated_at
        for field, value in spec["related"].items():
            assert body[field] == value

        repeated = await client.put(
            f"{spec['collection']}/{entity_id}", headers=context["headers"], json=spec["update"]
        )
        assert repeated.status_code == 200

        listing = await client.get(
            spec["collection"], headers=context["headers"], params=spec.get("list_query")
        )
        assert listing.status_code == 200
        stored = next(item for item in listing.json()["items"] if item["id"] == entity_id)
        assert stored["updated_at"] >= created_updated_at
        for field, value in spec["related"].items():
            assert stored[field] == value

        if spec["public"] is not None:
            public = await client.get(spec["public"], headers=context["public_headers"])
            assert public.status_code == 200
            assert entity_id in {item["id"] for item in spec["public_items"](public.json())}
            if detail_path := spec.get("detail"):
                detail = await client.get(detail_path(body), headers=context["public_headers"])
                assert detail.status_code == 200
                assert detail.json()["id"] == entity_id

        if spec.get("duplicate_slug"):
            duplicate = await client.post(
                spec["collection"], headers=context["headers"], json=spec["update"]
            )
            assert duplicate.status_code == 409

        archived = await client.delete(
            f"/api/v1/admin/{family}/{entity_id}", headers=context["headers"]
        )
        assert archived.status_code == 204
        after_archive = await client.put(
            f"{spec['collection']}/{entity_id}", headers=context["headers"], json=spec["update"]
        )
        assert after_archive.status_code == 409
        assert after_archive.json()["code"] == "ADMIN_RESOURCE_ARCHIVED"

        if spec["public"] is not None:
            public_after = await client.get(spec["public"], headers=context["public_headers"])
            assert public_after.status_code == 200
            assert entity_id not in {
                item["id"] for item in spec["public_items"](public_after.json())
            }
            if detail_path := spec.get("detail"):
                missing_detail = await client.get(
                    detail_path(body), headers=context["public_headers"]
                )
                assert missing_detail.status_code == 404

    await context["app"].state.database.dispose()


async def test_school_profile_can_be_replaced_and_losslessly_reset(
    admin_content_context: dict[str, Any],
) -> None:
    context = admin_content_context
    transport = httpx.ASGITransport(app=context["app"])
    profile = {
        "profile": {"display_name": "Disposable school", "description": "Temporary profile"},
        "addresses": [{"label": "Main", "address": "Test address"}],
        "phones": [{"label": "Office", "phone_number": "02100000000"}],
        "social_links": [{"platform": "website", "url": "https://example.test"}],
    }
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        initial = await client.get("/api/v1/public/site", headers=context["public_headers"])
        assert initial.status_code == 200
        assert initial.json()["profile"] is None

        replaced = await client.put(
            "/api/v1/admin/school-profile", headers=context["headers"], json=profile
        )
        assert replaced.status_code == 204
        visible = await client.get("/api/v1/public/site", headers=context["public_headers"])
        assert visible.status_code == 200
        assert visible.json()["profile"]["display_name"] == "Disposable school"
        assert len(visible.json()["addresses"]) == 1
        assert len(visible.json()["phones"]) == 1
        assert len(visible.json()["social_links"]) == 1

        reset = await client.delete("/api/v1/admin/school-profile", headers=context["headers"])
        assert reset.status_code == 204
        restored = await client.get("/api/v1/public/site", headers=context["public_headers"])
        assert restored.status_code == 200
        assert restored.json()["profile"] is None
        assert restored.json()["addresses"] == []
        assert restored.json()["phones"] == []
        assert restored.json()["social_links"] == []

        repeated = await client.delete("/api/v1/admin/school-profile", headers=context["headers"])
        assert repeated.status_code == 204

    await context["app"].state.database.dispose()


async def test_gallery_item_invalid_album_and_media_are_structured_client_errors(
    admin_content_context: dict[str, Any],
) -> None:
    context = admin_content_context
    transport = httpx.ASGITransport(app=context["app"])
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        missing_album = await client.post(
            f"/api/v1/admin/gallery/{uuid.uuid4()}/items",
            headers=context["headers"],
            json={"media_id": str(context["image_id"])},
        )
        assert missing_album.status_code == 404

        album = await client.post(
            "/api/v1/admin/gallery",
            headers=context["headers"],
            json={
                "title": "Gallery relationship test",
                "slug": f"gallery-relationship-{uuid.uuid4().hex}",
                "status": "DRAFT",
            },
        )
        assert album.status_code == 201
        invalid_media = await client.post(
            f"/api/v1/admin/gallery/{album.json()['id']}/items",
            headers=context["headers"],
            json={"media_id": str(uuid.uuid4())},
        )
        assert invalid_media.status_code == 409
        assert invalid_media.json()["code"] == "ADMIN_RESOURCE_CONFLICT"
    await context["app"].state.database.dispose()
