from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_permission
from app.auth.permissions import Permission
from app.core.errors import ApplicationError
from app.media.models import MediaAsset
from app.media.schemas import (
    MediaResponse,
    UploadCompleteRequest,
    UploadInitiateRequest,
    UploadInitiateResponse,
)
from app.media.storage import ObjectStorage
from app.tenancy.context import TenantContext, tenant_context_from_request
from app.tenancy.dependencies import tenant_session

admin_router = APIRouter(prefix="/api/v1/admin/media", tags=["admin-media"])
public_router = APIRouter(prefix="/api/v1/public/media", tags=["public-media"])

MIME_EXTENSIONS = {
    "image/jpeg": frozenset({".jpg", ".jpeg"}),
    "image/png": frozenset({".png"}),
    "image/webp": frozenset({".webp"}),
    "application/pdf": frozenset({".pdf"}),
}


@admin_router.post(
    "/uploads",
    response_model=UploadInitiateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.CONTENT_WRITE))],
)
async def initiate_upload(
    body: UploadInitiateRequest,
    request: Request,
    tenant: TenantContext = Depends(tenant_context_from_request),
    session: AsyncSession = Depends(tenant_session),
) -> UploadInitiateResponse:
    settings = request.app.state.settings
    extension = Path(body.filename).suffix.casefold()
    allowed_extensions = MIME_EXTENSIONS.get(body.mime_type)
    if (
        body.mime_type not in settings.upload_allowed_mime_types
        or allowed_extensions is None
        or extension not in allowed_extensions
    ):
        raise ApplicationError(
            "MEDIA_TYPE_NOT_ALLOWED", "File type is not allowed.", status_code=422
        )
    if body.size_bytes > settings.upload_max_bytes:
        raise ApplicationError(
            "MEDIA_TOO_LARGE", "File exceeds the upload size limit.", status_code=413
        )
    media_id = uuid.uuid4()
    object_key = f"tenants/{tenant.tenant_id}/{media_id}/{uuid.uuid4().hex}{extension}"
    media = MediaAsset(
        id=media_id,
        tenant_id=tenant.tenant_id,
        object_key=object_key,
        original_filename=body.filename,
        mime_type=body.mime_type,
        size_bytes=body.size_bytes,
        alt_text=body.alt_text,
        status="PENDING",
        visibility=body.visibility,
    )
    session.add(media)
    storage: ObjectStorage = request.app.state.object_storage
    upload = await storage.presign_upload(
        object_key=object_key, mime_type=body.mime_type, max_bytes=settings.upload_max_bytes
    )
    await session.flush()
    return UploadInitiateResponse(
        media_id=media.id,
        upload_url=upload.url,
        form_fields=upload.fields,
        expires_in=settings.s3_presign_ttl_seconds,
    )


@admin_router.post(
    "/uploads/{media_id}/complete",
    response_model=MediaResponse,
    dependencies=[Depends(require_permission(Permission.CONTENT_WRITE))],
)
async def complete_upload(
    media_id: uuid.UUID,
    body: UploadCompleteRequest,
    request: Request,
    session: AsyncSession = Depends(tenant_session),
) -> MediaAsset:
    media = await session.get(MediaAsset, media_id, with_for_update=True)
    if media is None:
        raise ApplicationError("MEDIA_NOT_FOUND", "Media asset was not found.", status_code=404)
    if media.status == "READY":
        return media
    storage: ObjectStorage = request.app.state.object_storage
    stored = await storage.inspect(object_key=media.object_key)
    if stored is None:
        raise ApplicationError(
            "MEDIA_OBJECT_NOT_UPLOADED",
            "The uploaded object is not available yet.",
            status_code=409,
        )
    if stored.size_bytes != media.size_bytes or stored.content_type != media.mime_type:
        media.status = "REJECTED"
        raise ApplicationError(
            "MEDIA_UPLOAD_MISMATCH",
            "Uploaded object does not match its declaration.",
            status_code=422,
        )
    media.sha256 = body.sha256.casefold() if body.sha256 else None
    media.width = body.width
    media.height = body.height
    media.status = "READY"
    await session.flush()
    return media


@public_router.get("/{media_id}", response_class=RedirectResponse)
async def download_media(
    media_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(tenant_session),
) -> RedirectResponse:
    media = await session.get(MediaAsset, media_id)
    if media is None or media.status != "READY" or media.visibility != "PUBLIC":
        raise ApplicationError("MEDIA_NOT_FOUND", "Media asset was not found.", status_code=404)
    storage: ObjectStorage = request.app.state.object_storage
    url = await storage.presign_download(
        object_key=media.object_key, filename=media.original_filename, disposition="inline"
    )
    return RedirectResponse(url=url, status_code=307)
