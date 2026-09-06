from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import Principal, require_permission
from app.auth.permissions import Permission
from app.content.admin_schemas import (
    BannerAdmin,
    ContactRequestAdmin,
    ContactRequestAdminUpdate,
    ExamOfferingAdmin,
    ExamOfferingWrite,
    GalleryAlbumAdmin,
    GalleryAlbumWrite,
    GalleryItemAdmin,
    GalleryItemWrite,
    HonorAdmin,
    HonorCategoryAdmin,
    HonorCategoryWrite,
    HonorWrite,
    PostAdmin,
    PricingPlanAdmin,
    PricingPlanWrite,
    ProfileContactsWrite,
    SampleExamAdmin,
    SampleExamWrite,
    StaffAdmin,
    StaffWrite,
)
from app.content.admin_service import AdminContentService
from app.content.models import (
    Banner,
    ContactRequest,
    GalleryAlbum,
    Honor,
    HonorCategory,
    Post,
    SampleExam,
    StaffMember,
)
from app.content.schemas import BannerWrite, PostWrite
from app.core.errors import ApplicationError
from app.core.models import Base
from app.core.pagination import Page, PageParams
from app.exams.models import ExamOffering, ExamPricingPlan, PricingPlan
from app.tenancy.context import TenantContext, tenant_context_from_request
from app.tenancy.dependencies import require_feature, tenant_session
from app.tenancy.features import ensure_feature_enabled

router = APIRouter(prefix="/api/v1/admin", tags=["admin-content"])


def post_feature(kind: str) -> str:
    return {"NEWS": "news", "ANNOUNCEMENT": "announcements", "BLOG": "blog"}[kind]


async def _create[ResponseT: BaseModel](
    model: type[Base],
    response_schema: type[ResponseT],
    body: BaseModel,
    tenant: TenantContext,
    principal: Principal,
    session: AsyncSession,
    entity_type: str,
) -> ResponseT:
    try:
        entity = await AdminContentService().create(
            session,
            model,
            tenant_id=tenant.tenant_id,
            body=body,
            actor_user_id=principal.user_id,
            entity_type=entity_type,
        )
    except IntegrityError as exc:
        raise ApplicationError(
            "ADMIN_RESOURCE_CONFLICT",
            "Resource conflicts with an existing record or relationship.",
            status_code=409,
        ) from exc
    return response_schema.model_validate(entity, from_attributes=True)


async def _list[ResponseT: BaseModel](
    model: type[Base],
    response_schema: type[ResponseT],
    page: PageParams,
    session: AsyncSession,
) -> Page[ResponseT]:
    rows, total = await AdminContentService().list(
        session, model, offset=page.offset, limit=page.page_size
    )
    return Page(
        items=[response_schema.model_validate(row, from_attributes=True) for row in rows],
        page=page.page,
        page_size=page.page_size,
        total=total,
    )


async def _update[ResponseT: BaseModel](
    model: type[Base],
    response_schema: type[ResponseT],
    entity_id: uuid.UUID,
    body: BaseModel,
    tenant: TenantContext,
    principal: Principal,
    session: AsyncSession,
    entity_type: str,
) -> ResponseT:
    service = AdminContentService()
    try:
        entity = await service.get(session, model, entity_id, lock=True)
        await service.update(
            session,
            entity,
            body=body,
            tenant_id=tenant.tenant_id,
            actor_user_id=principal.user_id,
            entity_type=entity_type,
        )
    except IntegrityError as exc:
        raise ApplicationError(
            "ADMIN_RESOURCE_CONFLICT",
            "Resource conflicts with an existing record or relationship.",
            status_code=409,
        ) from exc
    return response_schema.model_validate(entity, from_attributes=True)


@router.get("/posts", response_model=Page[PostAdmin])
async def list_posts(
    kind: Literal["NEWS", "ANNOUNCEMENT"],
    page: PageParams = Depends(),
    tenant: TenantContext = Depends(tenant_context_from_request),
    _: Principal = Depends(require_permission(Permission.CONTENT_READ)),
    session: AsyncSession = Depends(tenant_session),
) -> Page[Any]:
    await ensure_feature_enabled(
        session, tenant_id=tenant.tenant_id, feature_key=post_feature(kind)
    )
    rows, total = await AdminContentService().list(
        session,
        Post,
        offset=page.offset,
        limit=page.page_size,
        filters={"kind": kind},
    )
    return Page(
        items=[PostAdmin.model_validate(row, from_attributes=True) for row in rows],
        page=page.page,
        page_size=page.page_size,
        total=total,
    )


@router.post("/posts", response_model=PostAdmin, status_code=201)
async def create_post(
    body: PostWrite,
    tenant: TenantContext = Depends(tenant_context_from_request),
    principal: Principal = Depends(require_permission(Permission.CONTENT_WRITE)),
    session: AsyncSession = Depends(tenant_session),
) -> PostAdmin:
    if body.kind == "BLOG":
        raise ApplicationError(
            "BLOG_ENDPOINT_REQUIRED",
            "Use the dedicated blog draft and publication endpoints.",
            status_code=422,
        )
    await ensure_feature_enabled(
        session, tenant_id=tenant.tenant_id, feature_key=post_feature(body.kind)
    )
    return await _create(Post, PostAdmin, body, tenant, principal, session, "post")


@router.put("/posts/{entity_id}", response_model=PostAdmin)
async def update_post(
    entity_id: uuid.UUID,
    body: PostWrite,
    tenant: TenantContext = Depends(tenant_context_from_request),
    principal: Principal = Depends(require_permission(Permission.CONTENT_WRITE)),
    session: AsyncSession = Depends(tenant_session),
) -> PostAdmin:
    if body.kind == "BLOG":
        raise ApplicationError(
            "BLOG_ENDPOINT_REQUIRED",
            "Use the dedicated blog draft and publication endpoints.",
            status_code=422,
        )
    await ensure_feature_enabled(
        session, tenant_id=tenant.tenant_id, feature_key=post_feature(body.kind)
    )
    service = AdminContentService()
    entity = await service.get(session, Post, entity_id, lock=True)
    if entity.kind == "BLOG":
        raise ApplicationError(
            "BLOG_ENDPOINT_REQUIRED",
            "Use the dedicated blog draft and publication endpoints.",
            status_code=422,
        )
    try:
        await service.update(
            session,
            entity,
            body=body,
            tenant_id=tenant.tenant_id,
            actor_user_id=principal.user_id,
            entity_type="post",
        )
    except IntegrityError as exc:
        raise ApplicationError(
            "ADMIN_RESOURCE_CONFLICT",
            "Resource conflicts with an existing record or relationship.",
            status_code=409,
        ) from exc
    return PostAdmin.model_validate(entity, from_attributes=True)


@router.get(
    "/banners", response_model=Page[BannerAdmin], dependencies=[Depends(require_feature("banners"))]
)
async def list_banners(
    page: PageParams = Depends(),
    _: Principal = Depends(require_permission(Permission.CONTENT_READ)),
    session: AsyncSession = Depends(tenant_session),
) -> Page[Any]:
    return await _list(Banner, BannerAdmin, page, session)


@router.post(
    "/banners",
    response_model=BannerAdmin,
    status_code=201,
    dependencies=[Depends(require_feature("banners"))],
)
async def create_banner(
    body: BannerWrite,
    tenant: TenantContext = Depends(tenant_context_from_request),
    principal: Principal = Depends(require_permission(Permission.CONTENT_WRITE)),
    session: AsyncSession = Depends(tenant_session),
) -> BannerAdmin:
    return await _create(Banner, BannerAdmin, body, tenant, principal, session, "banner")


@router.get(
    "/honor-categories",
    response_model=Page[HonorCategoryAdmin],
    dependencies=[Depends(require_feature("honors"))],
)
async def list_honor_categories(
    page: PageParams = Depends(),
    _: Principal = Depends(require_permission(Permission.CONTENT_READ)),
    session: AsyncSession = Depends(tenant_session),
) -> Page[Any]:
    return await _list(HonorCategory, HonorCategoryAdmin, page, session)


@router.post(
    "/honor-categories",
    response_model=HonorCategoryAdmin,
    status_code=201,
    dependencies=[Depends(require_feature("honors"))],
)
async def create_honor_category(
    body: HonorCategoryWrite,
    tenant: TenantContext = Depends(tenant_context_from_request),
    principal: Principal = Depends(require_permission(Permission.CONTENT_WRITE)),
    session: AsyncSession = Depends(tenant_session),
) -> HonorCategoryAdmin:
    return await _create(
        HonorCategory, HonorCategoryAdmin, body, tenant, principal, session, "honor_category"
    )


@router.get(
    "/honors", response_model=Page[HonorAdmin], dependencies=[Depends(require_feature("honors"))]
)
async def list_honors(
    page: PageParams = Depends(),
    _: Principal = Depends(require_permission(Permission.CONTENT_READ)),
    session: AsyncSession = Depends(tenant_session),
) -> Page[Any]:
    return await _list(Honor, HonorAdmin, page, session)


@router.post(
    "/honors",
    response_model=HonorAdmin,
    status_code=201,
    dependencies=[Depends(require_feature("honors"))],
)
async def create_honor(
    body: HonorWrite,
    tenant: TenantContext = Depends(tenant_context_from_request),
    principal: Principal = Depends(require_permission(Permission.CONTENT_WRITE)),
    session: AsyncSession = Depends(tenant_session),
) -> HonorAdmin:
    return await _create(Honor, HonorAdmin, body, tenant, principal, session, "honor")


@router.get(
    "/staff", response_model=Page[StaffAdmin], dependencies=[Depends(require_feature("staff"))]
)
async def list_staff(
    page: PageParams = Depends(),
    _: Principal = Depends(require_permission(Permission.CONTENT_READ)),
    session: AsyncSession = Depends(tenant_session),
) -> Page[Any]:
    return await _list(StaffMember, StaffAdmin, page, session)


@router.post(
    "/staff",
    response_model=StaffAdmin,
    status_code=201,
    dependencies=[Depends(require_feature("staff"))],
)
async def create_staff(
    body: StaffWrite,
    tenant: TenantContext = Depends(tenant_context_from_request),
    principal: Principal = Depends(require_permission(Permission.CONTENT_WRITE)),
    session: AsyncSession = Depends(tenant_session),
) -> StaffAdmin:
    return await _create(StaffMember, StaffAdmin, body, tenant, principal, session, "staff_member")


@router.get(
    "/pricing-plans",
    response_model=Page[PricingPlanAdmin],
    dependencies=[Depends(require_feature("pricing"))],
)
async def list_pricing(
    page: PageParams = Depends(),
    _: Principal = Depends(require_permission(Permission.CONTENT_READ)),
    session: AsyncSession = Depends(tenant_session),
) -> Page[Any]:
    return await _list(PricingPlan, PricingPlanAdmin, page, session)


@router.post(
    "/pricing-plans",
    response_model=PricingPlanAdmin,
    status_code=201,
    dependencies=[Depends(require_feature("pricing"))],
)
async def create_pricing(
    body: PricingPlanWrite,
    tenant: TenantContext = Depends(tenant_context_from_request),
    principal: Principal = Depends(require_permission(Permission.CONTENT_WRITE)),
    session: AsyncSession = Depends(tenant_session),
) -> PricingPlanAdmin:
    return await _create(
        PricingPlan, PricingPlanAdmin, body, tenant, principal, session, "pricing_plan"
    )


@router.get("/exams", response_model=Page[ExamOfferingAdmin])
async def list_exams(
    page: PageParams = Depends(),
    _: Principal = Depends(require_permission(Permission.CONTENT_READ)),
    session: AsyncSession = Depends(tenant_session),
) -> Page[Any]:
    result = await _list(ExamOffering, ExamOfferingAdmin, page, session)
    plan_ids_by_exam: dict[uuid.UUID, list[uuid.UUID]] = {item.id: [] for item in result.items}
    if plan_ids_by_exam:
        associations = (
            await session.execute(
                select(ExamPricingPlan.exam_offering_id, ExamPricingPlan.pricing_plan_id).where(
                    ExamPricingPlan.exam_offering_id.in_(plan_ids_by_exam)
                )
            )
        ).all()
        for exam_id, plan_id in associations:
            plan_ids_by_exam[exam_id].append(plan_id)
    for item in result.items:
        item.pricing_plan_ids = plan_ids_by_exam[item.id]
    return result


@router.post("/exams", response_model=ExamOfferingAdmin, status_code=201)
async def create_exam(
    body: ExamOfferingWrite,
    tenant: TenantContext = Depends(tenant_context_from_request),
    principal: Principal = Depends(require_permission(Permission.CONTENT_WRITE)),
    session: AsyncSession = Depends(tenant_session),
) -> ExamOfferingAdmin:
    service = AdminContentService()
    try:
        entity = await service.create(
            session,
            ExamOffering,
            tenant_id=tenant.tenant_id,
            body=body,
            actor_user_id=principal.user_id,
            entity_type="exam_offering",
        )
        await service.set_exam_plans(session, entity, body.pricing_plan_ids)
    except IntegrityError as exc:
        raise ApplicationError(
            "ADMIN_RESOURCE_CONFLICT",
            "Resource conflicts with an existing record or relationship.",
            status_code=409,
        ) from exc
    response = ExamOfferingAdmin.model_validate(entity, from_attributes=True)
    response.pricing_plan_ids = body.pricing_plan_ids
    return response


@router.get(
    "/sample-exams",
    response_model=Page[SampleExamAdmin],
    dependencies=[Depends(require_feature("sample_exams"))],
)
async def list_sample_exams(
    page: PageParams = Depends(),
    _: Principal = Depends(require_permission(Permission.CONTENT_READ)),
    session: AsyncSession = Depends(tenant_session),
) -> Page[Any]:
    return await _list(SampleExam, SampleExamAdmin, page, session)


@router.post(
    "/sample-exams",
    response_model=SampleExamAdmin,
    status_code=201,
    dependencies=[Depends(require_feature("sample_exams"))],
)
async def create_sample_exam(
    body: SampleExamWrite,
    tenant: TenantContext = Depends(tenant_context_from_request),
    principal: Principal = Depends(require_permission(Permission.CONTENT_WRITE)),
    session: AsyncSession = Depends(tenant_session),
) -> SampleExamAdmin:
    return await _create(
        SampleExam,
        SampleExamAdmin,
        body,
        tenant,
        principal,
        session,
        "sample_exam",
    )


@router.get(
    "/gallery",
    response_model=Page[GalleryAlbumAdmin],
    dependencies=[Depends(require_feature("gallery"))],
)
async def list_gallery(
    page: PageParams = Depends(),
    _: Principal = Depends(require_permission(Permission.CONTENT_READ)),
    session: AsyncSession = Depends(tenant_session),
) -> Page[Any]:
    return await _list(GalleryAlbum, GalleryAlbumAdmin, page, session)


@router.post(
    "/gallery",
    response_model=GalleryAlbumAdmin,
    status_code=201,
    dependencies=[Depends(require_feature("gallery"))],
)
async def create_gallery(
    body: GalleryAlbumWrite,
    tenant: TenantContext = Depends(tenant_context_from_request),
    principal: Principal = Depends(require_permission(Permission.CONTENT_WRITE)),
    session: AsyncSession = Depends(tenant_session),
) -> GalleryAlbumAdmin:
    return await _create(
        GalleryAlbum, GalleryAlbumAdmin, body, tenant, principal, session, "gallery_album"
    )


@router.post(
    "/gallery/{album_id}/items",
    response_model=GalleryItemAdmin,
    status_code=201,
    dependencies=[Depends(require_feature("gallery"))],
)
async def create_gallery_item(
    album_id: uuid.UUID,
    body: GalleryItemWrite,
    tenant: TenantContext = Depends(tenant_context_from_request),
    principal: Principal = Depends(require_permission(Permission.CONTENT_WRITE)),
    session: AsyncSession = Depends(tenant_session),
) -> GalleryItemAdmin:
    service = AdminContentService()
    await service.get(session, GalleryAlbum, album_id)
    try:
        item = await service.add_gallery_item(
            session,
            tenant_id=tenant.tenant_id,
            album_id=album_id,
            body=body,
            actor_user_id=principal.user_id,
        )
    except IntegrityError as exc:
        raise ApplicationError(
            "ADMIN_RESOURCE_CONFLICT",
            "Resource conflicts with an existing record or relationship.",
            status_code=409,
        ) from exc
    return GalleryItemAdmin.model_validate(item, from_attributes=True)


@router.put(
    "/school-profile", status_code=204, dependencies=[Depends(require_feature("school_profile"))]
)
async def replace_school_profile(
    body: ProfileContactsWrite,
    tenant: TenantContext = Depends(tenant_context_from_request),
    principal: Principal = Depends(require_permission(Permission.PROFILE_WRITE)),
    session: AsyncSession = Depends(tenant_session),
) -> Response:
    await AdminContentService().replace_profile(
        session,
        tenant_id=tenant.tenant_id,
        actor_user_id=principal.user_id,
        body=body,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/school-profile", status_code=204, dependencies=[Depends(require_feature("school_profile"))]
)
async def reset_school_profile(
    tenant: TenantContext = Depends(tenant_context_from_request),
    principal: Principal = Depends(require_permission(Permission.PROFILE_WRITE)),
    session: AsyncSession = Depends(tenant_session),
) -> Response:
    await AdminContentService().reset_profile(
        session,
        tenant_id=tenant.tenant_id,
        actor_user_id=principal.user_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/contact-requests",
    response_model=Page[ContactRequestAdmin],
    dependencies=[Depends(require_feature("contact_requests"))],
)
async def list_contact_requests(
    page: PageParams = Depends(),
    _: Principal = Depends(require_permission(Permission.CONTACT_READ)),
    session: AsyncSession = Depends(tenant_session),
) -> Page[Any]:
    return await _list(ContactRequest, ContactRequestAdmin, page, session)


@router.patch(
    "/contact-requests/{entity_id}",
    response_model=ContactRequestAdmin,
    dependencies=[Depends(require_feature("contact_requests"))],
)
async def handle_contact_request(
    entity_id: uuid.UUID,
    body: ContactRequestAdminUpdate,
    principal: Principal = Depends(require_permission(Permission.REGISTRATION_WRITE)),
    session: AsyncSession = Depends(tenant_session),
) -> ContactRequestAdmin:
    service = AdminContentService()
    contact = await service.get(session, ContactRequest, entity_id, lock=True)
    await service.handle_contact_request(
        session, contact=contact, body=body, actor_user_id=principal.user_id
    )
    return ContactRequestAdmin.model_validate(contact, from_attributes=True)


@router.put(
    "/banners/{entity_id}",
    response_model=BannerAdmin,
    dependencies=[Depends(require_feature("banners"))],
)
async def update_banner(
    entity_id: uuid.UUID,
    body: BannerWrite,
    tenant: TenantContext = Depends(tenant_context_from_request),
    principal: Principal = Depends(require_permission(Permission.CONTENT_WRITE)),
    session: AsyncSession = Depends(tenant_session),
) -> BannerAdmin:
    return await _update(Banner, BannerAdmin, entity_id, body, tenant, principal, session, "banner")


@router.put(
    "/honor-categories/{entity_id}",
    response_model=HonorCategoryAdmin,
    dependencies=[Depends(require_feature("honors"))],
)
async def update_honor_category(
    entity_id: uuid.UUID,
    body: HonorCategoryWrite,
    tenant: TenantContext = Depends(tenant_context_from_request),
    principal: Principal = Depends(require_permission(Permission.CONTENT_WRITE)),
    session: AsyncSession = Depends(tenant_session),
) -> HonorCategoryAdmin:
    return await _update(
        HonorCategory,
        HonorCategoryAdmin,
        entity_id,
        body,
        tenant,
        principal,
        session,
        "honor_category",
    )


@router.put(
    "/honors/{entity_id}",
    response_model=HonorAdmin,
    dependencies=[Depends(require_feature("honors"))],
)
async def update_honor(
    entity_id: uuid.UUID,
    body: HonorWrite,
    tenant: TenantContext = Depends(tenant_context_from_request),
    principal: Principal = Depends(require_permission(Permission.CONTENT_WRITE)),
    session: AsyncSession = Depends(tenant_session),
) -> HonorAdmin:
    return await _update(Honor, HonorAdmin, entity_id, body, tenant, principal, session, "honor")


@router.put(
    "/staff/{entity_id}",
    response_model=StaffAdmin,
    dependencies=[Depends(require_feature("staff"))],
)
async def update_staff(
    entity_id: uuid.UUID,
    body: StaffWrite,
    tenant: TenantContext = Depends(tenant_context_from_request),
    principal: Principal = Depends(require_permission(Permission.CONTENT_WRITE)),
    session: AsyncSession = Depends(tenant_session),
) -> StaffAdmin:
    return await _update(
        StaffMember,
        StaffAdmin,
        entity_id,
        body,
        tenant,
        principal,
        session,
        "staff_member",
    )


@router.put(
    "/pricing-plans/{entity_id}",
    response_model=PricingPlanAdmin,
    dependencies=[Depends(require_feature("pricing"))],
)
async def update_pricing_plan(
    entity_id: uuid.UUID,
    body: PricingPlanWrite,
    tenant: TenantContext = Depends(tenant_context_from_request),
    principal: Principal = Depends(require_permission(Permission.CONTENT_WRITE)),
    session: AsyncSession = Depends(tenant_session),
) -> PricingPlanAdmin:
    return await _update(
        PricingPlan,
        PricingPlanAdmin,
        entity_id,
        body,
        tenant,
        principal,
        session,
        "pricing_plan",
    )


@router.put("/exams/{entity_id}", response_model=ExamOfferingAdmin)
async def update_exam(
    entity_id: uuid.UUID,
    body: ExamOfferingWrite,
    tenant: TenantContext = Depends(tenant_context_from_request),
    principal: Principal = Depends(require_permission(Permission.CONTENT_WRITE)),
    session: AsyncSession = Depends(tenant_session),
) -> ExamOfferingAdmin:
    service = AdminContentService()
    entity = await service.get(session, ExamOffering, entity_id, lock=True)
    try:
        await service.update(
            session,
            entity,
            body=body,
            tenant_id=tenant.tenant_id,
            actor_user_id=principal.user_id,
            entity_type="exam_offering",
        )
        await service.set_exam_plans(session, entity, body.pricing_plan_ids)
    except IntegrityError as exc:
        raise ApplicationError(
            "ADMIN_RESOURCE_CONFLICT",
            "Resource conflicts with an existing record or relationship.",
            status_code=409,
        ) from exc
    response = ExamOfferingAdmin.model_validate(entity, from_attributes=True)
    response.pricing_plan_ids = body.pricing_plan_ids
    return response


@router.put(
    "/sample-exams/{entity_id}",
    response_model=SampleExamAdmin,
    dependencies=[Depends(require_feature("sample_exams"))],
)
async def update_sample_exam(
    entity_id: uuid.UUID,
    body: SampleExamWrite,
    tenant: TenantContext = Depends(tenant_context_from_request),
    principal: Principal = Depends(require_permission(Permission.CONTENT_WRITE)),
    session: AsyncSession = Depends(tenant_session),
) -> SampleExamAdmin:
    return await _update(
        SampleExam,
        SampleExamAdmin,
        entity_id,
        body,
        tenant,
        principal,
        session,
        "sample_exam",
    )


@router.put(
    "/gallery/{entity_id}",
    response_model=GalleryAlbumAdmin,
    dependencies=[Depends(require_feature("gallery"))],
)
async def update_gallery_album(
    entity_id: uuid.UUID,
    body: GalleryAlbumWrite,
    tenant: TenantContext = Depends(tenant_context_from_request),
    principal: Principal = Depends(require_permission(Permission.CONTENT_WRITE)),
    session: AsyncSession = Depends(tenant_session),
) -> GalleryAlbumAdmin:
    return await _update(
        GalleryAlbum,
        GalleryAlbumAdmin,
        entity_id,
        body,
        tenant,
        principal,
        session,
        "gallery_album",
    )


RESOURCE_MODELS = {
    "posts": (Post, "post", None),
    "banners": (Banner, "banner", "banners"),
    "honor-categories": (HonorCategory, "honor_category", "honors"),
    "honors": (Honor, "honor", "honors"),
    "staff": (StaffMember, "staff_member", "staff"),
    "pricing-plans": (PricingPlan, "pricing_plan", "pricing"),
    "exams": (ExamOffering, "exam_offering", "exam_registration"),
    "sample-exams": (SampleExam, "sample_exam", "sample_exams"),
    "gallery": (GalleryAlbum, "gallery_album", "gallery"),
}


@router.delete("/{resource}/{entity_id}", status_code=204)
async def archive_resource(
    resource: str,
    entity_id: uuid.UUID,
    tenant: TenantContext = Depends(tenant_context_from_request),
    principal: Principal = Depends(require_permission(Permission.CONTENT_WRITE)),
    session: AsyncSession = Depends(tenant_session),
) -> Response:
    mapping = RESOURCE_MODELS.get(resource)
    if mapping is None:
        raise ApplicationError(
            "ADMIN_RESOURCE_NOT_FOUND", "Resource was not found.", status_code=404
        )
    model, entity_type, feature_key = mapping
    service = AdminContentService()
    entity = await service.get(session, model, entity_id, lock=True)
    if isinstance(entity, Post):
        feature_key = {
            "NEWS": "news",
            "ANNOUNCEMENT": "announcements",
            "BLOG": "blog",
        }[entity.kind]
    assert feature_key is not None
    await ensure_feature_enabled(session, tenant_id=tenant.tenant_id, feature_key=feature_key)
    await service.archive_or_delete(
        session,
        entity,
        tenant_id=tenant.tenant_id,
        actor_user_id=principal.user_id,
        entity_type=entity_type,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
