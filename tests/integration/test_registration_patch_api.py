from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from app.auth.models import TenantMembership, User
from app.auth.security import create_access_token
from app.content.models import SchoolDirectoryEntry
from app.core.config import Settings
from app.exams.models import ExamOffering, ExamPricingPlan, PricingPlan
from app.main import create_app
from app.media.models import MediaAsset
from app.tenancy.models import Tenant, TenantDomain, TenantFeature

pytestmark = pytest.mark.integration


@pytest.fixture
async def patch_api_context(owner_engine: AsyncEngine, settings: Settings) -> dict[str, Any]:
    tenant_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    exam_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    media_id = uuid.uuid4()
    current_school_id = uuid.uuid4()
    previous_school_id = uuid.uuid4()
    host = f"patch-{tenant_id}.example.test"
    now = datetime.now(UTC)
    async with owner_engine.begin() as connection:
        await connection.execute(
            insert(Tenant),
            {
                "id": tenant_id,
                "name": "Registration patch tenant",
                "slug": f"patch-{tenant_id}",
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
            {
                "tenant_id": tenant_id,
                "feature_key": "exam_registration",
                "enabled": True,
                "configuration": {},
            },
        )
        await connection.execute(
            insert(User),
            {
                "id": admin_id,
                "email": f"patch-admin-{admin_id}@example.test",
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
            insert(SchoolDirectoryEntry),
            [
                {"id": current_school_id, "name": "Current school", "is_active": True},
                {"id": previous_school_id, "name": "Previous school", "is_active": True},
            ],
        )
        await connection.execute(
            insert(MediaAsset),
            {
                "id": media_id,
                "tenant_id": tenant_id,
                "object_key": f"tenants/{tenant_id}/profile.png",
                "original_filename": "profile.png",
                "mime_type": "image/png",
                "size_bytes": 68,
                "status": "READY",
                "visibility": "PRIVATE",
            },
        )
        await connection.execute(
            insert(PricingPlan),
            {
                "id": plan_id,
                "tenant_id": tenant_id,
                "title": "Patch plan",
                "slug": f"patch-plan-{plan_id}",
                "description": "Patch plan",
                "mode": "ONLINE",
                "amount": 0,
                "currency": "IRR",
                "features": [],
                "sort_order": 0,
                "is_featured": False,
                "status": "PUBLISHED",
            },
        )
        await connection.execute(
            insert(ExamOffering),
            {
                "id": exam_id,
                "tenant_id": tenant_id,
                "title": "Patch exam",
                "slug": f"patch-exam-{exam_id}",
                "description": "Patch exam",
                "mode": "ONLINE",
                "status": "REGISTRATION_OPEN",
            },
        )
        await connection.execute(
            insert(ExamPricingPlan),
            {
                "tenant_id": tenant_id,
                "exam_offering_id": exam_id,
                "pricing_plan_id": plan_id,
            },
        )
    admin_token, _ = create_access_token(
        settings,
        user_id=admin_id,
        tenant_id=tenant_id,
        is_platform_admin=False,
    )
    app = create_app(settings)
    return {
        "app": app,
        "host": host,
        "tenant_id": tenant_id,
        "exam_id": exam_id,
        "plan_id": plan_id,
        "media_id": media_id,
        "current_school_id": current_school_id,
        "previous_school_id": previous_school_id,
        "admin_token": admin_token,
    }


async def create_draft(
    client: httpx.AsyncClient, context: dict[str, Any], phone: str
) -> tuple[str, str]:
    response = await client.post(
        "/api/v1/public/registrations",
        headers={"Host": context["host"]},
        json={
            "exam_offering_id": str(context["exam_id"]),
            "selected_pricing_plan_id": str(context["plan_id"]),
            "phone_number": phone,
        },
    )
    assert response.status_code == 201
    body = response.json()
    return body["registration"]["id"], body["draft_token"]


def draft_headers(context: dict[str, Any], token: str) -> dict[str, str]:
    return {"Host": context["host"], "Authorization": f"Draft {token}"}


async def test_patch_each_supported_field_and_combined_values_persist(
    patch_api_context: dict[str, Any],
) -> None:
    context = patch_api_context
    transport = httpx.ASGITransport(app=context["app"])
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        registration_id, token = await create_draft(client, context, "09123456789")
        headers = draft_headers(context, token)
        expected: dict[str, Any] = {}
        updates = [
            ("phone_number", "+989123456788", "+989123456788"),
            ("first_name", "Ali", "Ali"),
            ("last_name", "Ahmadi", "Ahmadi"),
            ("gender", "MALE", "MALE"),
            ("national_code", "1234567891", "1234567891"),
            ("father_name", "Reza", "Reza"),
            ("birth_date", "2010-01-01", "2010-01-01"),
            ("home_phone", "02112345678", "02112345678"),
            (
                "current_school_id",
                str(context["current_school_id"]),
                str(context["current_school_id"]),
            ),
            (
                "previous_school_id",
                str(context["previous_school_id"]),
                str(context["previous_school_id"]),
            ),
            ("postal_code", "1234567890", "1234567890"),
            ("address", "Tehran, Example Street", "Tehran, Example Street"),
            ("profile_image_id", str(context["media_id"]), str(context["media_id"])),
            ("extra_answers", {"grade": "nine"}, {"grade": "nine"}),
        ]
        previous_updated_at: str | None = None
        for field, value, normalized in updates:
            response = await client.patch(
                f"/api/v1/public/registrations/{registration_id}",
                headers=headers,
                json={field: value},
            )
            assert response.status_code == 200, field
            body = response.json()
            expected[field] = normalized
            for expected_field, expected_value in expected.items():
                assert body[expected_field] == expected_value
            if previous_updated_at is not None:
                assert body["updated_at"] >= previous_updated_at
            previous_updated_at = body["updated_at"]

            fresh = await client.get(
                f"/api/v1/public/registrations/{registration_id}", headers=headers
            )
            assert fresh.status_code == 200
            assert fresh.json()[field] == normalized

        combined = await client.patch(
            f"/api/v1/public/registrations/{registration_id}",
            headers=headers,
            json={"first_name": "Sara", "last_name": "Karimi", "extra_answers": {"grade": "ten"}},
        )
        assert combined.status_code == 200
        assert combined.json()["first_name"] == "Sara"
        assert combined.json()["last_name"] == "Karimi"
        assert combined.json()["postal_code"] == "1234567890"

    await context["app"].state.database.dispose()


async def test_patch_draft_authorization_rotation_substitution_and_immutable_states(
    patch_api_context: dict[str, Any],
) -> None:
    context = patch_api_context
    transport = httpx.ASGITransport(app=context["app"])
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first_id, first_token = await create_draft(client, context, "09123456789")
        second_id, second_token = await create_draft(client, context, "09123456788")
        path = f"/api/v1/public/registrations/{first_id}"
        cases = [
            ({"Host": context["host"]}, 401),
            ({"Host": context["host"], "Authorization": "Draft malformed"}, 401),
            (draft_headers(context, secrets.token_urlsafe(48)), 404),
            (draft_headers(context, second_token), 404),
        ]
        for headers, expected_status in cases:
            response = await client.patch(path, headers=headers, json={"first_name": "Denied"})
            assert response.status_code == expected_status
            assert response.json()["code"] != "INTERNAL_SERVER_ERROR"

        rotated = await client.post(
            f"{path}/token/rotate", headers=draft_headers(context, first_token)
        )
        assert rotated.status_code == 200
        replacement = rotated.json()["draft_token"]
        old = await client.patch(
            path, headers=draft_headers(context, first_token), json={"first_name": "Denied"}
        )
        assert old.status_code == 404
        wrong_registration = await client.patch(
            f"/api/v1/public/registrations/{second_id}",
            headers=draft_headers(context, replacement),
            json={"first_name": "Denied"},
        )
        assert wrong_registration.status_code == 404

        admin_headers = {
            "Host": context["host"],
            "Authorization": f"Bearer {context['admin_token']}",
        }
        cancelled = await client.patch(
            f"/api/v1/admin/registrations/{first_id}",
            headers=admin_headers,
            json={"status": "CANCELLED"},
        )
        assert cancelled.status_code == 200
        immutable = await client.patch(
            path,
            headers=draft_headers(context, replacement),
            json={"first_name": "Denied"},
        )
        assert immutable.status_code == 400
        assert immutable.json()["code"] == "REGISTRATION_NOT_EDITABLE"

        submitted = await client.patch(
            f"/api/v1/admin/registrations/{first_id}",
            headers=admin_headers,
            json={"status": "SUBMITTED"},
        )
        assert submitted.status_code == 200
        still_immutable = await client.patch(
            path,
            headers=draft_headers(context, replacement),
            json={"last_name": "Denied"},
        )
        assert still_immutable.status_code == 400

    await context["app"].state.database.dispose()


@pytest.mark.parametrize(
    "payload",
    [
        {"gender": "INVALID"},
        {"birth_date": "2999-01-01"},
        {"current_school_id": "not-a-uuid"},
        {"first_name": ""},
        {"last_name": "x" * 101},
        {"address": "tiny"},
        {"postal_code": "123"},
        {"national_code": "1234567890"},
        {"unknown_field": "forbidden"},
    ],
)
async def test_patch_validation_boundaries_are_structured_422(
    patch_api_context: dict[str, Any], payload: dict[str, Any]
) -> None:
    context = patch_api_context
    transport = httpx.ASGITransport(app=context["app"])
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        registration_id, token = await create_draft(client, context, "09123456789")
        response = await client.patch(
            f"/api/v1/public/registrations/{registration_id}",
            headers=draft_headers(context, token),
            json=payload,
        )
    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"
    await context["app"].state.database.dispose()


async def test_patch_invalid_related_ids_are_structured_422(
    patch_api_context: dict[str, Any],
) -> None:
    context = patch_api_context
    transport = httpx.ASGITransport(app=context["app"])
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        registration_id, token = await create_draft(client, context, "09123456789")
        for field in ("current_school_id", "previous_school_id", "profile_image_id"):
            response = await client.patch(
                f"/api/v1/public/registrations/{registration_id}",
                headers=draft_headers(context, token),
                json={field: str(uuid.uuid4())},
            )
            assert response.status_code == 422, field
            assert response.json()["code"] == "REGISTRATION_REFERENCE_INVALID"
    await context["app"].state.database.dispose()
