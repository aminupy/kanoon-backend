from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.auth.dependencies import Principal, require_permission
from app.auth.permissions import Permission
from app.core.pagination import Page, PageParams
from app.site_builds.models import SiteBuildRequest
from app.site_builds.schemas import SiteBuildHistoryItem, SiteBuildStatus
from app.site_builds.service import SiteBuildService
from app.tenancy.context import TenantContext, tenant_context_from_request
from app.tenancy.dependencies import tenant_session

router = APIRouter(prefix="/api/v1/admin/site-build", tags=["admin-site-build"])


@router.get("/status", response_model=SiteBuildStatus)
async def build_status(
    _: Principal = Depends(require_permission(Permission.SITE_BUILD_READ)),
    session: AsyncSession = Depends(tenant_session),
) -> SiteBuildStatus:
    return await SiteBuildService().status(session)


@router.get("/history", response_model=Page[SiteBuildHistoryItem])
async def build_history(
    page: PageParams = Depends(),
    _: Principal = Depends(require_permission(Permission.SITE_BUILD_READ)),
    session: AsyncSession = Depends(tenant_session),
) -> Page[Any]:
    total = await session.scalar(select(func.count()).select_from(SiteBuildRequest)) or 0
    requests = list(
        (
            await session.scalars(
                select(SiteBuildRequest)
                .order_by(desc(SiteBuildRequest.requested_at), desc(SiteBuildRequest.id))
                .offset(page.offset)
                .limit(page.page_size)
            )
        ).all()
    )
    return Page(
        items=[
            SiteBuildHistoryItem.model_validate(item, from_attributes=True) for item in requests
        ],
        page=page.page,
        page_size=page.page_size,
        total=total,
    )


@router.post("/rebuild", response_model=SiteBuildStatus, status_code=202)
async def manual_rebuild(
    tenant: TenantContext = Depends(tenant_context_from_request),
    principal: Principal = Depends(require_permission(Permission.SITE_BUILD_REQUEST)),
    session: AsyncSession = Depends(tenant_session),
) -> SiteBuildStatus:
    request = await SiteBuildService().manual_rebuild(
        session, tenant_id=tenant.tenant_id, created_by=principal.user_id
    )
    session.add(
        AuditEvent(
            tenant_id=tenant.tenant_id,
            actor_user_id=principal.user_id,
            action="site_build.manual_requested",
            entity_type="site_build_request",
            entity_id=request.id,
            metadata_={"target_revision": request.target_revision},
            created_at=datetime.now(UTC),
        )
    )
    await session.flush()
    return await SiteBuildService().status(session)
