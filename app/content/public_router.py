from __future__ import annotations

import hashlib
import hmac
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.content.models import (
    Banner,
    ContactRequest,
    GalleryAlbum,
    GalleryItem,
    Honor,
    Post,
    SampleExam,
    SchoolDirectoryEntry,
    StaffMember,
)
from app.content.schemas import (
    BannerPublic,
    ContactRequestAccepted,
    ContactRequestCreate,
    ExamOfferingPublic,
    GalleryAlbumDetail,
    GalleryAlbumPublic,
    GalleryItemPublic,
    HonorPublic,
    PostDetail,
    PostSummary,
    PricingPlanPublic,
    PublicAddress,
    PublicPhone,
    PublicSocialLink,
    SampleExamPublic,
    SchoolDirectoryPublic,
    SiteBootstrap,
    SiteProfile,
    SiteTenant,
    StaffPublic,
)
from app.core.errors import ApplicationError
from app.core.pagination import Page, PageParams
from app.exams.models import ExamOffering, PricingPlan
from app.tenancy.context import TenantContext, tenant_context_from_request
from app.tenancy.dependencies import require_feature, tenant_session
from app.tenancy.models import (
    TenantAddress,
    TenantFeature,
    TenantPhone,
    TenantProfile,
    TenantSocialLink,
)

router = APIRouter(prefix="/api/v1/public", tags=["public-content"])


def _from_attributes[SchemaT: BaseModel](
    schema: type[SchemaT], rows: Iterable[object]
) -> list[SchemaT]:
    return [schema.model_validate(row, from_attributes=True) for row in rows]


@router.get("/site", response_model=SiteBootstrap)
async def site_bootstrap(
    tenant: TenantContext = Depends(tenant_context_from_request),
    session: AsyncSession = Depends(tenant_session),
) -> SiteBootstrap:
    profile = await session.scalar(select(TenantProfile).limit(1))
    features = list(
        (
            await session.scalars(
                select(TenantFeature.feature_key)
                .where(TenantFeature.enabled.is_(True))
                .order_by(TenantFeature.feature_key)
            )
        ).all()
    )
    addresses = list(
        (await session.scalars(select(TenantAddress).order_by(TenantAddress.sort_order))).all()
    )
    phones = list(
        (await session.scalars(select(TenantPhone).order_by(TenantPhone.sort_order))).all()
    )
    socials = list(
        (
            await session.scalars(select(TenantSocialLink).order_by(TenantSocialLink.sort_order))
        ).all()
    )
    return SiteBootstrap(
        tenant=SiteTenant(
            name=profile.display_name if profile else tenant.slug,
            slug=tenant.slug,
            locale=tenant.default_locale,
            timezone=tenant.timezone,
            currency=tenant.default_currency,
        ),
        profile=SiteProfile.model_validate(profile, from_attributes=True) if profile else None,
        enabled_capabilities=features,
        addresses=_from_attributes(PublicAddress, addresses),
        phones=_from_attributes(PublicPhone, phones),
        social_links=_from_attributes(PublicSocialLink, socials),
    )


@router.get(
    "/banners",
    response_model=list[BannerPublic],
    dependencies=[Depends(require_feature("banners"))],
)
async def banners(session: AsyncSession = Depends(tenant_session)) -> list[BannerPublic]:
    now = datetime.now(UTC)
    rows = list(
        (
            await session.scalars(
                select(Banner)
                .where(
                    Banner.status == "PUBLISHED",
                    or_(Banner.starts_at.is_(None), Banner.starts_at <= now),
                    or_(Banner.ends_at.is_(None), Banner.ends_at > now),
                )
                .order_by(Banner.sort_order, Banner.id)
            )
        ).all()
    )
    return _from_attributes(BannerPublic, rows)


async def _post_page(
    session: AsyncSession, kind: Literal["NEWS", "ANNOUNCEMENT", "BLOG"], page: PageParams
) -> Page[PostSummary]:
    where = (Post.kind == kind, Post.status == "PUBLISHED", Post.published_at <= datetime.now(UTC))
    total = await session.scalar(select(func.count()).select_from(Post).where(*where)) or 0
    rows = list(
        (
            await session.scalars(
                select(Post)
                .where(*where)
                .order_by(Post.published_at.desc(), Post.id)
                .offset(page.offset)
                .limit(page.page_size)
            )
        ).all()
    )
    return Page(
        items=_from_attributes(PostSummary, rows),
        page=page.page,
        page_size=page.page_size,
        total=total,
    )


async def _post_detail(
    session: AsyncSession, kind: Literal["NEWS", "ANNOUNCEMENT", "BLOG"], slug: str
) -> PostDetail:
    row = await session.scalar(
        select(Post).where(
            Post.kind == kind,
            Post.slug == slug,
            Post.status == "PUBLISHED",
            Post.published_at <= datetime.now(UTC),
        )
    )
    if row is None:
        raise ApplicationError("CONTENT_NOT_FOUND", "Content was not found.", status_code=404)
    return PostDetail.model_validate(row, from_attributes=True)


@router.get(
    "/news", response_model=Page[PostSummary], dependencies=[Depends(require_feature("news"))]
)
async def news(
    page: PageParams = Depends(), session: AsyncSession = Depends(tenant_session)
) -> Page[PostSummary]:
    return await _post_page(session, "NEWS", page)


@router.get(
    "/news/{slug}", response_model=PostDetail, dependencies=[Depends(require_feature("news"))]
)
async def news_detail(slug: str, session: AsyncSession = Depends(tenant_session)) -> PostDetail:
    return await _post_detail(session, "NEWS", slug)


@router.get(
    "/announcements",
    response_model=Page[PostSummary],
    dependencies=[Depends(require_feature("announcements"))],
)
async def announcements(
    page: PageParams = Depends(), session: AsyncSession = Depends(tenant_session)
) -> Page[PostSummary]:
    return await _post_page(session, "ANNOUNCEMENT", page)


@router.get(
    "/announcements/{slug}",
    response_model=PostDetail,
    dependencies=[Depends(require_feature("announcements"))],
)
async def announcement_detail(
    slug: str, session: AsyncSession = Depends(tenant_session)
) -> PostDetail:
    return await _post_detail(session, "ANNOUNCEMENT", slug)


@router.get(
    "/honors", response_model=Page[HonorPublic], dependencies=[Depends(require_feature("honors"))]
)
async def honors(
    page: PageParams = Depends(), session: AsyncSession = Depends(tenant_session)
) -> Page[HonorPublic]:
    total = (
        await session.scalar(
            select(func.count()).select_from(Honor).where(Honor.status == "PUBLISHED")
        )
        or 0
    )
    rows = list(
        (
            await session.scalars(
                select(Honor)
                .where(Honor.status == "PUBLISHED")
                .order_by(Honor.sort_order, Honor.id)
                .offset(page.offset)
                .limit(page.page_size)
            )
        ).all()
    )
    return Page(
        items=_from_attributes(HonorPublic, rows),
        page=page.page,
        page_size=page.page_size,
        total=total,
    )


@router.get(
    "/staff", response_model=list[StaffPublic], dependencies=[Depends(require_feature("staff"))]
)
async def staff(session: AsyncSession = Depends(tenant_session)) -> list[StaffPublic]:
    rows = list(
        (
            await session.scalars(
                select(StaffMember)
                .where(StaffMember.is_active.is_(True))
                .order_by(StaffMember.sort_order, StaffMember.id)
            )
        ).all()
    )
    return _from_attributes(StaffPublic, rows)


@router.get(
    "/pricing-plans",
    response_model=list[PricingPlanPublic],
    dependencies=[Depends(require_feature("pricing"))],
)
async def pricing_plans(session: AsyncSession = Depends(tenant_session)) -> list[PricingPlanPublic]:
    rows = list(
        (
            await session.scalars(
                select(PricingPlan)
                .where(PricingPlan.status == "PUBLISHED")
                .order_by(PricingPlan.sort_order, PricingPlan.id)
            )
        ).all()
    )
    return _from_attributes(PricingPlanPublic, rows)


@router.get("/exams", response_model=list[ExamOfferingPublic])
async def exams(session: AsyncSession = Depends(tenant_session)) -> list[ExamOfferingPublic]:
    rows = list(
        (
            await session.scalars(
                select(ExamOffering)
                .where(ExamOffering.status == "REGISTRATION_OPEN")
                .order_by(ExamOffering.registration_starts_at, ExamOffering.id)
            )
        ).all()
    )
    return _from_attributes(ExamOfferingPublic, rows)


@router.get("/school-directory", response_model=Page[SchoolDirectoryPublic])
async def school_directory(
    page: PageParams = Depends(),
    search: str | None = None,
    session: AsyncSession = Depends(tenant_session),
) -> Page[SchoolDirectoryPublic]:
    statement = select(SchoolDirectoryEntry).where(SchoolDirectoryEntry.is_active.is_(True))
    count_statement = (
        select(func.count())
        .select_from(SchoolDirectoryEntry)
        .where(SchoolDirectoryEntry.is_active.is_(True))
    )
    if search:
        pattern = f"%{search[:100]}%"
        statement = statement.where(SchoolDirectoryEntry.name.ilike(pattern))
        count_statement = count_statement.where(SchoolDirectoryEntry.name.ilike(pattern))
    total = await session.scalar(count_statement) or 0
    rows = list(
        (
            await session.scalars(
                statement.order_by(SchoolDirectoryEntry.name)
                .offset(page.offset)
                .limit(page.page_size)
            )
        ).all()
    )
    return Page(
        items=_from_attributes(SchoolDirectoryPublic, rows),
        page=page.page,
        page_size=page.page_size,
        total=total,
    )


@router.get(
    "/sample-exams",
    response_model=Page[SampleExamPublic],
    dependencies=[Depends(require_feature("sample_exams"))],
)
async def sample_exams(
    page: PageParams = Depends(), session: AsyncSession = Depends(tenant_session)
) -> Page[SampleExamPublic]:
    total = (
        await session.scalar(
            select(func.count()).select_from(SampleExam).where(SampleExam.status == "PUBLISHED")
        )
        or 0
    )
    rows = list(
        (
            await session.scalars(
                select(SampleExam)
                .where(SampleExam.status == "PUBLISHED")
                .order_by(SampleExam.sort_order, SampleExam.id)
                .offset(page.offset)
                .limit(page.page_size)
            )
        ).all()
    )
    return Page(
        items=_from_attributes(SampleExamPublic, rows),
        page=page.page,
        page_size=page.page_size,
        total=total,
    )


@router.get(
    "/gallery",
    response_model=Page[GalleryAlbumPublic],
    dependencies=[Depends(require_feature("gallery"))],
)
async def gallery(
    page: PageParams = Depends(), session: AsyncSession = Depends(tenant_session)
) -> Page[GalleryAlbumPublic]:
    total = (
        await session.scalar(
            select(func.count()).select_from(GalleryAlbum).where(GalleryAlbum.status == "PUBLISHED")
        )
        or 0
    )
    rows = list(
        (
            await session.scalars(
                select(GalleryAlbum)
                .where(GalleryAlbum.status == "PUBLISHED")
                .order_by(GalleryAlbum.sort_order, GalleryAlbum.id)
                .offset(page.offset)
                .limit(page.page_size)
            )
        ).all()
    )
    return Page(
        items=_from_attributes(GalleryAlbumPublic, rows),
        page=page.page,
        page_size=page.page_size,
        total=total,
    )


@router.get(
    "/gallery/{slug}",
    response_model=GalleryAlbumDetail,
    dependencies=[Depends(require_feature("gallery"))],
)
async def gallery_detail(
    slug: str, session: AsyncSession = Depends(tenant_session)
) -> GalleryAlbumDetail:
    album = await session.scalar(
        select(GalleryAlbum).where(GalleryAlbum.slug == slug, GalleryAlbum.status == "PUBLISHED")
    )
    if album is None:
        raise ApplicationError("GALLERY_NOT_FOUND", "Gallery album was not found.", status_code=404)
    items = list(
        (
            await session.scalars(
                select(GalleryItem)
                .where(GalleryItem.album_id == album.id)
                .order_by(GalleryItem.sort_order, GalleryItem.id)
            )
        ).all()
    )
    base = GalleryAlbumPublic.model_validate(album, from_attributes=True)
    return GalleryAlbumDetail(**base.model_dump(), items=_from_attributes(GalleryItemPublic, items))


@router.post(
    "/contact-requests",
    response_model=ContactRequestAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_feature("contact_requests"))],
)
async def create_contact_request(
    body: ContactRequestCreate,
    request: Request,
    tenant: TenantContext = Depends(tenant_context_from_request),
    session: AsyncSession = Depends(tenant_session),
) -> ContactRequestAccepted:
    ip = request.client.host if request.client else "unknown"
    ip_hash = hmac.new(
        request.app.state.settings.signing_key.get_secret_value().encode(),
        ip.encode(),
        hashlib.sha256,
    ).hexdigest()
    since = datetime.now(UTC) - timedelta(hours=1)
    for scope in (f"contact:ip:{tenant.tenant_id}:{ip_hash}", f"contact:phone:{body.phone_number}"):
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
            {"scope": scope},
        )
    attempts = await session.scalar(
        select(func.count())
        .select_from(ContactRequest)
        .where(
            ContactRequest.created_at >= since,
            or_(
                ContactRequest.request_ip_hash == ip_hash,
                ContactRequest.phone_number == body.phone_number,
            ),
        )
    )
    if (attempts or 0) >= 5:
        raise ApplicationError(
            "CONTACT_REQUEST_RATE_LIMITED",
            "Too many contact requests. Try again later.",
            status_code=429,
        )
    contact = ContactRequest(
        tenant_id=tenant.tenant_id,
        name=body.name,
        education_level=body.education_level,
        phone_number=body.phone_number,
        request_ip_hash=ip_hash,
        status="NEW",
        created_at=datetime.now(UTC),
    )
    session.add(contact)
    await session.flush()
    return ContactRequestAccepted(id=contact.id, status=contact.status)
