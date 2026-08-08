from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import Principal, require_permission
from app.auth.permissions import Permission
from app.core.database import Database
from app.core.pagination import Page, PageParams
from app.registrations.admin_schemas import (
    ContactAdmin,
    RegistrationAdminDetail,
    RegistrationAdminSummary,
    RegistrationAdminUpdate,
)
from app.registrations.admin_service import (
    RegistrationAdminService,
    stream_registration_csv,
)
from app.tenancy.context import TenantContext, tenant_context_from_request
from app.tenancy.dependencies import get_database, require_feature, tenant_session

router = APIRouter(
    prefix="/api/v1/admin/registrations",
    tags=["admin-registrations"],
    dependencies=[Depends(require_feature("exam_registration"))],
)


@router.get("", response_model=Page[RegistrationAdminSummary])
async def list_registrations(
    page: PageParams = Depends(),
    registration_status: str | None = Query(default=None, alias="status", max_length=32),
    search: str | None = Query(default=None, min_length=2, max_length=100),
    _: Principal = Depends(require_permission(Permission.REGISTRATION_READ)),
    session: AsyncSession = Depends(tenant_session),
) -> Page[RegistrationAdminSummary]:
    rows, total = await RegistrationAdminService().list(
        session,
        status=registration_status,
        search=search,
        offset=page.offset,
        limit=page.page_size,
    )
    return Page(
        items=[RegistrationAdminSummary.model_validate(row, from_attributes=True) for row in rows],
        page=page.page,
        page_size=page.page_size,
        total=total,
    )


@router.get("/export.csv")
async def export_registrations(
    tenant: TenantContext = Depends(tenant_context_from_request),
    principal: Principal = Depends(require_permission(Permission.REGISTRATION_EXPORT)),
    database: Database = Depends(get_database),
) -> StreamingResponse:
    async with database.tenant_session(tenant.tenant_id) as session:
        await RegistrationAdminService().record_export(
            session, tenant_id=tenant.tenant_id, actor_user_id=principal.user_id
        )
    return StreamingResponse(
        stream_registration_csv(database, tenant.tenant_id),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="registrations.csv"'},
    )


@router.get("/{registration_id}", response_model=RegistrationAdminDetail)
async def registration_detail(
    registration_id: uuid.UUID,
    _: Principal = Depends(require_permission(Permission.REGISTRATION_READ)),
    session: AsyncSession = Depends(tenant_session),
) -> RegistrationAdminDetail:
    service = RegistrationAdminService()
    registration = await service.get(session, registration_id)
    contacts = await service.contacts(session, registration.id)
    summary = RegistrationAdminDetail.model_validate(
        {
            **RegistrationAdminSummary.model_validate(
                registration, from_attributes=True
            ).model_dump(),
            "gender": registration.gender,
            "father_name": registration.father_name,
            "birth_date": registration.birth_date,
            "home_phone": registration.home_phone,
            "current_school_id": registration.current_school_id,
            "previous_school_id": registration.previous_school_id,
            "postal_code": registration.postal_code,
            "address": registration.address,
            "profile_image_id": registration.profile_image_id,
            "payable_amount": registration.payable_amount,
            "payable_currency": registration.payable_currency,
            "phone_verified_at": registration.phone_verified_at,
            "internal_notes": registration.internal_notes,
            "contacts": [
                ContactAdmin.model_validate(item, from_attributes=True) for item in contacts
            ],
        }
    )
    return summary


@router.patch("/{registration_id}", response_model=RegistrationAdminDetail)
async def update_registration(
    registration_id: uuid.UUID,
    body: RegistrationAdminUpdate,
    request: Request,
    principal: Principal = Depends(require_permission(Permission.REGISTRATION_WRITE)),
    session: AsyncSession = Depends(tenant_session),
) -> RegistrationAdminDetail:
    del request
    service = RegistrationAdminService()
    registration = await service.get(session, registration_id, lock=True)
    await service.update(
        session, registration=registration, body=body, actor_user_id=principal.user_id
    )
    contacts = await service.contacts(session, registration.id)
    data = RegistrationAdminSummary.model_validate(registration, from_attributes=True).model_dump()
    return RegistrationAdminDetail(
        **data,
        gender=registration.gender,
        father_name=registration.father_name,
        birth_date=registration.birth_date,
        home_phone=registration.home_phone,
        current_school_id=registration.current_school_id,
        previous_school_id=registration.previous_school_id,
        postal_code=registration.postal_code,
        address=registration.address,
        profile_image_id=registration.profile_image_id,
        payable_amount=registration.payable_amount,
        payable_currency=registration.payable_currency,
        phone_verified_at=registration.phone_verified_at,
        internal_notes=registration.internal_notes,
        contacts=[ContactAdmin.model_validate(item, from_attributes=True) for item in contacts],
    )
