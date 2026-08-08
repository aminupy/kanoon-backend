from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Database
from app.core.errors import ApplicationError
from app.media.models import MediaAsset
from app.media.router import MIME_EXTENSIONS
from app.media.schemas import (
    MediaResponse,
    UploadCompleteRequest,
    UploadInitiateRequest,
    UploadInitiateResponse,
)
from app.media.storage import ObjectStorage
from app.otp.provider import OTPProvider
from app.otp.service import OTPService
from app.registrations.schemas import (
    DraftCreated,
    DraftTokenRotated,
    OTPSendResponse,
    OTPVerifyRequest,
    OTPVerifyResponse,
    RegistrationContactResponse,
    RegistrationContactsPut,
    RegistrationCreate,
    RegistrationPatch,
    RegistrationResponse,
)
from app.registrations.service import RegistrationService
from app.tenancy.context import TenantContext, tenant_context_from_request
from app.tenancy.dependencies import get_database, require_feature, tenant_session

router = APIRouter(
    prefix="/api/v1/public/registrations",
    tags=["public-registrations"],
    dependencies=[Depends(require_feature("exam_registration"))],
)


def draft_token(authorization: str | None = Header(default=None)) -> str:
    if authorization is None:
        raise ApplicationError(
            "DRAFT_AUTH_REQUIRED", "Draft authorization is required.", status_code=401
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.casefold() != "draft" or len(token) < 32:
        raise ApplicationError(
            "DRAFT_AUTH_REQUIRED", "Draft authorization is required.", status_code=401
        )
    return token


async def _response(
    service: RegistrationService,
    session: AsyncSession,
    registration: object,
) -> RegistrationResponse:
    response = RegistrationResponse.model_validate(registration, from_attributes=True)
    contacts = await service.contacts(session, response.id)
    return response.model_copy(
        update={
            "contacts": [
                RegistrationContactResponse.model_validate(item, from_attributes=True)
                for item in contacts
            ]
        }
    )


@router.post("", response_model=DraftCreated, status_code=status.HTTP_201_CREATED)
async def create_registration(
    body: RegistrationCreate,
    request: Request,
    tenant: TenantContext = Depends(tenant_context_from_request),
    session: AsyncSession = Depends(tenant_session),
) -> DraftCreated:
    service = RegistrationService(request.app.state.settings)
    registration, token = await service.create_draft(
        session,
        tenant_id=tenant.tenant_id,
        exam_offering_id=body.exam_offering_id,
        pricing_plan_id=body.selected_pricing_plan_id,
        phone_number=body.phone_number,
    )
    return DraftCreated(
        registration=await _response(service, session, registration), draft_token=token
    )


@router.get("/{registration_id}", response_model=RegistrationResponse)
async def get_registration(
    registration_id: uuid.UUID,
    request: Request,
    token: str = Depends(draft_token),
    session: AsyncSession = Depends(tenant_session),
) -> RegistrationResponse:
    service = RegistrationService(request.app.state.settings)
    registration = await service.authorized_draft(
        session, registration_id=registration_id, raw_token=token
    )
    return await _response(service, session, registration)


@router.patch("/{registration_id}", response_model=RegistrationResponse)
async def patch_registration(
    registration_id: uuid.UUID,
    body: RegistrationPatch,
    request: Request,
    token: str = Depends(draft_token),
    session: AsyncSession = Depends(tenant_session),
) -> RegistrationResponse:
    service = RegistrationService(request.app.state.settings)
    registration = await service.authorized_draft(
        session, registration_id=registration_id, raw_token=token, lock=True
    )
    try:
        await service.patch(session, registration, body)
    except IntegrityError as exc:
        raise ApplicationError(
            "DUPLICATE_EXAM_REGISTRATION",
            "This student is already registered for the exam.",
            status_code=409,
        ) from exc
    return await _response(service, session, registration)


@router.post("/{registration_id}/token/rotate", response_model=DraftTokenRotated)
async def rotate_draft_token(
    registration_id: uuid.UUID,
    request: Request,
    token: str = Depends(draft_token),
    session: AsyncSession = Depends(tenant_session),
) -> DraftTokenRotated:
    service = RegistrationService(request.app.state.settings)
    registration = await service.authorized_draft(
        session, registration_id=registration_id, raw_token=token, lock=True
    )
    replacement = await service.rotate_token(registration)
    await session.flush()
    return DraftTokenRotated(
        draft_token=replacement, expires_at=registration.draft_token_expires_at
    )


@router.post(
    "/{registration_id}/profile-image/upload",
    response_model=UploadInitiateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def initiate_profile_image_upload(
    registration_id: uuid.UUID,
    body: UploadInitiateRequest,
    request: Request,
    token: str = Depends(draft_token),
    tenant: TenantContext = Depends(tenant_context_from_request),
    session: AsyncSession = Depends(tenant_session),
) -> UploadInitiateResponse:
    service = RegistrationService(request.app.state.settings)
    registration = await service.authorized_draft(
        session, registration_id=registration_id, raw_token=token, lock=True
    )
    settings = request.app.state.settings
    extension = Path(body.filename).suffix.casefold()
    allowed_extensions = MIME_EXTENSIONS.get(body.mime_type)
    if (
        not body.mime_type.startswith("image/")
        or body.mime_type not in settings.upload_allowed_mime_types
        or allowed_extensions is None
        or extension not in allowed_extensions
    ):
        raise ApplicationError(
            "PROFILE_IMAGE_TYPE_NOT_ALLOWED", "Profile image type is not allowed.", status_code=422
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
        alt_text=None,
        status="PENDING",
        visibility="PRIVATE",
    )
    session.add(media)
    registration.profile_image_id = media.id
    storage: ObjectStorage = request.app.state.object_storage
    upload = await storage.presign_upload(
        object_key=object_key,
        mime_type=body.mime_type,
        max_bytes=settings.upload_max_bytes,
    )
    await session.flush()
    return UploadInitiateResponse(
        media_id=media.id,
        upload_url=upload.url,
        form_fields=upload.fields,
        expires_in=settings.s3_presign_ttl_seconds,
    )


@router.post(
    "/{registration_id}/profile-image/{media_id}/complete",
    response_model=MediaResponse,
)
async def complete_profile_image_upload(
    registration_id: uuid.UUID,
    media_id: uuid.UUID,
    body: UploadCompleteRequest,
    request: Request,
    token: str = Depends(draft_token),
    session: AsyncSession = Depends(tenant_session),
) -> MediaAsset:
    service = RegistrationService(request.app.state.settings)
    registration = await service.authorized_draft(
        session, registration_id=registration_id, raw_token=token, lock=True
    )
    if registration.profile_image_id != media_id:
        raise ApplicationError("MEDIA_NOT_FOUND", "Media asset was not found.", status_code=404)
    media = await session.get(MediaAsset, media_id, with_for_update=True)
    if media is None or media.visibility != "PRIVATE":
        raise ApplicationError("MEDIA_NOT_FOUND", "Media asset was not found.", status_code=404)
    if media.status == "READY":
        return media
    storage: ObjectStorage = request.app.state.object_storage
    stored = await storage.inspect(object_key=media.object_key)
    if stored.size_bytes != media.size_bytes or stored.content_type != media.mime_type:
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


@router.put("/{registration_id}/contacts", response_model=list[RegistrationContactResponse])
async def put_contacts(
    registration_id: uuid.UUID,
    body: RegistrationContactsPut,
    request: Request,
    token: str = Depends(draft_token),
    session: AsyncSession = Depends(tenant_session),
) -> list[RegistrationContactResponse]:
    service = RegistrationService(request.app.state.settings)
    registration = await service.authorized_draft(
        session, registration_id=registration_id, raw_token=token, lock=True
    )
    contacts = await service.replace_contacts(session, registration, body.contacts)
    return [
        RegistrationContactResponse.model_validate(item, from_attributes=True) for item in contacts
    ]


@router.post("/{registration_id}/otp/send", response_model=OTPSendResponse)
async def send_otp(
    registration_id: uuid.UUID,
    request: Request,
    token: str = Depends(draft_token),
    tenant: TenantContext = Depends(tenant_context_from_request),
    session: AsyncSession = Depends(tenant_session),
) -> OTPSendResponse:
    registration_service = RegistrationService(request.app.state.settings)
    registration = await registration_service.authorized_draft(
        session, registration_id=registration_id, raw_token=token, lock=True
    )
    provider: OTPProvider = request.app.state.otp_provider
    service = OTPService(request.app.state.settings, provider)
    challenge = await service.send(
        session,
        registration=registration,
        client_ip=request.client.host if request.client else "unknown",
        tenant_slug=tenant.slug,
    )
    return OTPSendResponse(
        expires_at=challenge.expires_at,
        resend_after_seconds=request.app.state.settings.otp_resend_cooldown_seconds,
    )


@router.post("/{registration_id}/otp/verify", response_model=OTPVerifyResponse)
async def verify_otp(
    registration_id: uuid.UUID,
    body: OTPVerifyRequest,
    request: Request,
    token: str = Depends(draft_token),
    tenant: TenantContext = Depends(tenant_context_from_request),
    database: Database = Depends(get_database),
) -> OTPVerifyResponse:
    deferred_error: ApplicationError | None = None
    verified_at = None
    async with database.tenant_session(tenant.tenant_id) as session:
        registration_service = RegistrationService(request.app.state.settings)
        registration = await registration_service.authorized_draft(
            session, registration_id=registration_id, raw_token=token, lock=True
        )
        service = OTPService(request.app.state.settings, request.app.state.otp_provider)
        try:
            verified_at = await service.verify(session, registration=registration, code=body.code)
        except ApplicationError as exc:
            deferred_error = exc
    if deferred_error is not None:
        raise deferred_error
    assert verified_at is not None
    return OTPVerifyResponse(verified=True, phone_verified_at=verified_at)


@router.post("/{registration_id}/submit", response_model=RegistrationResponse)
async def submit_registration(
    registration_id: uuid.UUID,
    request: Request,
    token: str = Depends(draft_token),
    session: AsyncSession = Depends(tenant_session),
) -> RegistrationResponse:
    service = RegistrationService(request.app.state.settings)
    registration = await service.authorized_draft(
        session, registration_id=registration_id, raw_token=token, lock=True
    )
    try:
        await service.submit(session, registration)
    except IntegrityError as exc:
        raise ApplicationError(
            "DUPLICATE_EXAM_REGISTRATION",
            "This student is already registered for the exam.",
            status_code=409,
        ) from exc
    return await _response(service, session, registration)
