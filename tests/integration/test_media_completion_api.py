from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import httpx
import pytest
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.auth.models import TenantMembership, User
from app.auth.security import create_access_token, token_digest
from app.core.config import Settings
from app.exams.models import ExamOffering
from app.main import create_app
from app.media.models import MediaAsset
from app.media.storage import PresignedUpload, StoredObject
from app.registrations.models import Registration
from app.tenancy.models import Tenant, TenantDomain, TenantFeature

pytestmark = pytest.mark.integration


class InspectableStorage:
    def __init__(self) -> None:
        self.objects: dict[str, StoredObject | None] = {}
        self.inspect_calls: dict[str, int] = {}

    async def inspect(self, *, object_key: str) -> StoredObject | None:
        self.inspect_calls[object_key] = self.inspect_calls.get(object_key, 0) + 1
        return self.objects.get(object_key)

    async def ensure_bucket(self) -> None:
        return None

    async def healthcheck(self) -> None:
        return None

    async def presign_upload(
        self, *, object_key: str, mime_type: str, max_bytes: int
    ) -> PresignedUpload:
        del object_key, mime_type, max_bytes
        raise NotImplementedError

    async def presign_download(
        self,
        *,
        object_key: str,
        filename: str,
        disposition: Literal["attachment", "inline"] = "attachment",
    ) -> str:
        del object_key, filename, disposition
        raise NotImplementedError

    async def delete(self, *, object_key: str) -> None:
        del object_key


@pytest.fixture
async def completion_context(owner_engine: AsyncEngine, settings: Settings) -> dict[str, Any]:
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    exam_id = uuid.uuid4()
    public_media_id = uuid.uuid4()
    private_media_id = uuid.uuid4()
    validation_media_id = uuid.uuid4()
    registration_id = uuid.uuid4()
    draft_token = secrets.token_urlsafe(48)
    host = f"media-completion-{tenant_id}.example.test"
    now = datetime.now(UTC)
    object_keys = {
        public_media_id: f"tenants/{tenant_id}/{public_media_id}/public.png",
        private_media_id: f"tenants/{tenant_id}/{private_media_id}/private.png",
        validation_media_id: f"tenants/{tenant_id}/{validation_media_id}/validation.png",
    }
    async with owner_engine.begin() as connection:
        await connection.execute(
            insert(Tenant),
            {
                "id": tenant_id,
                "name": "Media completion tenant",
                "slug": f"media-completion-{tenant_id}",
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
                "id": user_id,
                "email": f"media-completion-{user_id}@example.test",
                "password_hash": "!",
                "is_active": True,
                "is_platform_admin": False,
            },
        )
        await connection.execute(
            insert(TenantMembership),
            {
                "tenant_id": tenant_id,
                "user_id": user_id,
                "role": "TENANT_ADMIN",
                "created_at": now,
            },
        )
        await connection.execute(
            insert(ExamOffering),
            {
                "id": exam_id,
                "tenant_id": tenant_id,
                "title": "Completion test exam",
                "slug": f"completion-exam-{exam_id}",
                "description": "Completion test exam",
                "mode": "ONLINE",
                "status": "REGISTRATION_OPEN",
            },
        )
        await connection.execute(
            insert(MediaAsset),
            [
                {
                    "id": media_id,
                    "tenant_id": tenant_id,
                    "object_key": object_key,
                    "original_filename": "fixture.png",
                    "mime_type": "image/png",
                    "size_bytes": 68,
                    "status": "PENDING",
                    "visibility": "PRIVATE" if media_id == private_media_id else "PUBLIC",
                }
                for media_id, object_key in object_keys.items()
            ],
        )
        await connection.execute(
            insert(Registration),
            {
                "id": registration_id,
                "tenant_id": tenant_id,
                "exam_offering_id": exam_id,
                "draft_token_hash": token_digest(draft_token),
                "draft_token_expires_at": now + timedelta(hours=1),
                "phone_number": "+989123456789",
                "profile_image_id": private_media_id,
                "extra_answers": {},
                "status": "PHONE_VERIFICATION_REQUIRED",
                "payment_status": "PENDING",
            },
        )
    access_token, _ = create_access_token(
        settings,
        user_id=user_id,
        tenant_id=tenant_id,
        is_platform_admin=False,
    )
    storage = InspectableStorage()
    app = create_app(settings, object_storage=storage)
    return {
        "app": app,
        "tenant_id": tenant_id,
        "host": host,
        "admin_headers": {"Host": host, "Authorization": f"Bearer {access_token}"},
        "draft_headers": {"Host": host, "Authorization": f"Draft {draft_token}"},
        "public_media_id": public_media_id,
        "private_media_id": private_media_id,
        "validation_media_id": validation_media_id,
        "registration_id": registration_id,
        "object_keys": object_keys,
        "storage": storage,
    }


async def test_completion_boundaries_mismatches_ids_and_idempotency(
    completion_context: dict[str, Any],
) -> None:
    context = completion_context
    transport = httpx.ASGITransport(app=context["app"])
    admin_path = f"/api/v1/admin/media/uploads/{context['public_media_id']}/complete"
    valid_body = {"sha256": "a" * 64, "width": 1, "height": 1}
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        malformed_id = await client.post(
            "/api/v1/admin/media/uploads/not-a-uuid/complete",
            headers=context["admin_headers"],
            json=valid_body,
        )
        assert malformed_id.status_code == 422

        nonexistent = await client.post(
            f"/api/v1/admin/media/uploads/{uuid.uuid4()}/complete",
            headers=context["admin_headers"],
            json=valid_body,
        )
        assert nonexistent.status_code == 404
        assert nonexistent.json()["code"] == "MEDIA_NOT_FOUND"

        validation_path = f"/api/v1/admin/media/uploads/{context['validation_media_id']}/complete"
        for invalid_body in (
            {"sha256": "not-a-sha256"},
            {"width": 0},
            {"height": 50_001},
            {"width": "wide"},
        ):
            invalid = await client.post(
                validation_path,
                headers=context["admin_headers"],
                json=invalid_body,
            )
            assert invalid.status_code == 422
            assert invalid.json()["code"] == "REQUEST_VALIDATION_FAILED"

        public_key = context["object_keys"][context["public_media_id"]]
        context["storage"].objects[public_key] = StoredObject(
            size_bytes=67,
            content_type="image/png",
            metadata={},
        )
        wrong_size = await client.post(
            admin_path, headers=context["admin_headers"], json=valid_body
        )
        assert wrong_size.status_code == 422
        assert wrong_size.json()["code"] == "MEDIA_UPLOAD_MISMATCH"

        async with context["app"].state.database.tenant_session(context["tenant_id"]) as session:
            stored_media = await session.scalar(
                select(MediaAsset).where(MediaAsset.id == context["public_media_id"])
            )
            assert stored_media is not None and stored_media.status == "PENDING"

        context["storage"].objects[public_key] = StoredObject(
            size_bytes=68,
            content_type="application/octet-stream",
            metadata={},
        )
        wrong_mime = await client.post(
            admin_path, headers=context["admin_headers"], json=valid_body
        )
        assert wrong_mime.status_code == 422
        assert wrong_mime.json()["code"] == "MEDIA_UPLOAD_MISMATCH"

        async with context["app"].state.database.tenant_session(context["tenant_id"]) as session:
            stored_media = await session.scalar(
                select(MediaAsset).where(MediaAsset.id == context["public_media_id"])
            )
            assert stored_media is not None and stored_media.status == "PENDING"

        context["storage"].objects[public_key] = StoredObject(
            size_bytes=68,
            content_type="image/png",
            metadata={},
        )
        completed = await client.post(admin_path, headers=context["admin_headers"], json=valid_body)
        assert completed.status_code == 200
        assert completed.json()["status"] == "READY"
        calls_after_completion = context["storage"].inspect_calls[public_key]
        repeated = await client.post(
            admin_path,
            headers=context["admin_headers"],
            json={"sha256": "b" * 64, "width": 2, "height": 2},
        )
        assert repeated.status_code == 200
        assert repeated.json()["width"] == valid_body["width"]
        assert repeated.json()["height"] == valid_body["height"]
        assert context["storage"].inspect_calls[public_key] == calls_after_completion

        wrong_profile_media = await client.post(
            f"/api/v1/public/registrations/{context['registration_id']}/profile-image/"
            f"{context['public_media_id']}/complete",
            headers=context["draft_headers"],
            json=valid_body,
        )
        assert wrong_profile_media.status_code == 404

        private_key = context["object_keys"][context["private_media_id"]]
        context["storage"].objects[private_key] = StoredObject(
            size_bytes=68,
            content_type="image/jpeg",
            metadata={},
        )
        profile_path = (
            f"/api/v1/public/registrations/{context['registration_id']}/profile-image/"
            f"{context['private_media_id']}/complete"
        )
        wrong_profile_mime = await client.post(
            profile_path, headers=context["draft_headers"], json=valid_body
        )
        assert wrong_profile_mime.status_code == 422
        context["storage"].objects[private_key] = StoredObject(
            size_bytes=68,
            content_type="image/png",
            metadata={},
        )
        profile_complete = await client.post(
            profile_path, headers=context["draft_headers"], json=valid_body
        )
        assert profile_complete.status_code == 200
        assert profile_complete.json()["status"] == "READY"

    await context["app"].state.database.dispose()
