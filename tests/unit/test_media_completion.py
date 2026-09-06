from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from app.auth.security import token_digest
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.media.models import MediaAsset
from app.media.router import complete_upload
from app.media.schemas import UploadCompleteRequest
from app.media.storage import StoredObject
from app.registrations.models import Registration
from app.registrations.router import complete_profile_image_upload


class FakeStorage:
    def __init__(self) -> None:
        self.stored: StoredObject | None = None
        self.inspect_calls = 0

    async def inspect(self, *, object_key: str) -> StoredObject | None:
        del object_key
        self.inspect_calls += 1
        return self.stored


class FakeSession:
    def __init__(self, media: MediaAsset, registration: Registration | None = None) -> None:
        self.media = media
        self.registration = registration
        self.flush_calls = 0

    async def get(self, model: type[Any], entity_id: uuid.UUID, **_: Any) -> Any:
        del entity_id
        if model is MediaAsset:
            return self.media
        return None

    async def scalar(self, statement: Any) -> Registration | None:
        del statement
        return self.registration

    async def flush(self) -> None:
        self.flush_calls += 1


def pending_media(*, visibility: str) -> MediaAsset:
    return MediaAsset(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        object_key="tenants/test/pending.png",
        original_filename="pending.png",
        mime_type="image/png",
        size_bytes=68,
        status="PENDING",
        visibility=visibility,
    )


async def test_admin_missing_upload_is_conflict_retryable_and_completion_is_idempotent() -> None:
    media = pending_media(visibility="PUBLIC")
    storage = FakeStorage()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(object_storage=storage)))
    session = FakeSession(media)

    with pytest.raises(ApplicationError) as missing:
        await complete_upload(
            media.id,
            UploadCompleteRequest(sha256="a" * 64, width=1, height=1),
            request,  # type: ignore[arg-type]
            session,  # type: ignore[arg-type]
        )
    assert missing.value.status_code == 409
    assert missing.value.code == "MEDIA_OBJECT_NOT_UPLOADED"
    assert media.status == "PENDING"

    storage.stored = StoredObject(size_bytes=68, content_type="image/png", metadata={})
    completed = await complete_upload(
        media.id,
        UploadCompleteRequest(sha256="a" * 64, width=1, height=1),
        request,  # type: ignore[arg-type]
        session,  # type: ignore[arg-type]
    )
    assert completed.status == "READY"
    assert storage.inspect_calls == 2
    repeated = await complete_upload(
        media.id,
        UploadCompleteRequest(sha256="a" * 64, width=1, height=1),
        request,  # type: ignore[arg-type]
        session,  # type: ignore[arg-type]
    )
    assert repeated is completed
    assert storage.inspect_calls == 2


async def test_profile_missing_upload_is_conflict_and_remains_retryable() -> None:
    raw_token = secrets.token_urlsafe(48)
    media = pending_media(visibility="PRIVATE")
    registration = Registration(
        id=uuid.uuid4(),
        tenant_id=media.tenant_id,
        exam_offering_id=uuid.uuid4(),
        draft_token_hash=token_digest(raw_token),
        draft_token_expires_at=datetime.now(UTC) + timedelta(hours=1),
        phone_number="+989123456789",
        profile_image_id=media.id,
        extra_answers={},
        status="PHONE_VERIFICATION_REQUIRED",
        payment_status="PENDING",
    )
    storage = FakeStorage()
    state = SimpleNamespace(object_storage=storage, settings=Settings(environment="testing"))
    request = SimpleNamespace(app=SimpleNamespace(state=state))
    session = FakeSession(media, registration)

    with pytest.raises(ApplicationError) as missing:
        await complete_profile_image_upload(
            registration.id,
            media.id,
            UploadCompleteRequest(sha256="b" * 64, width=1, height=1),
            request,  # type: ignore[arg-type]
            raw_token,
            session,  # type: ignore[arg-type]
        )
    assert missing.value.status_code == 409
    assert missing.value.code == "MEDIA_OBJECT_NOT_UPLOADED"
    assert media.status == "PENDING"

    storage.stored = StoredObject(size_bytes=68, content_type="image/png", metadata={})
    completed = await complete_profile_image_upload(
        registration.id,
        media.id,
        UploadCompleteRequest(sha256="b" * 64, width=1, height=1),
        request,  # type: ignore[arg-type]
        raw_token,
        session,  # type: ignore[arg-type]
    )
    assert completed.status == "READY"
