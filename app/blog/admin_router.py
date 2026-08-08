from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import Principal, require_permission
from app.auth.permissions import Permission, role_has_permission
from app.blog.schemas import BlogAdmin, BlogCreate, BlogUpdate
from app.blog.service import BlogService
from app.content.models import Post
from app.core.errors import ApplicationError
from app.core.pagination import Page, PageParams
from app.tenancy.context import TenantContext, tenant_context_from_request
from app.tenancy.dependencies import require_feature, tenant_session

router = APIRouter(
    prefix="/api/v1/admin/blog",
    tags=["admin-blog"],
    dependencies=[Depends(require_feature("blog"))],
)


def _admin(post: Post) -> BlogAdmin:
    return BlogAdmin.model_validate(post, from_attributes=True)


def _require_publish(principal: Principal) -> None:
    if principal.is_platform_admin:
        return
    if principal.role is None or not role_has_permission(
        principal.role, Permission.CONTENT_PUBLISH
    ):
        raise ApplicationError("PERMISSION_DENIED", "Permission is denied.", status_code=403)


@router.get("", response_model=Page[BlogAdmin])
async def list_blog_posts(
    page: PageParams = Depends(),
    status: Literal["DRAFT", "PUBLISHED", "ARCHIVED"] | None = None,
    _: Principal = Depends(require_permission(Permission.CONTENT_READ)),
    session: AsyncSession = Depends(tenant_session),
) -> Page[Any]:
    filters = [Post.kind == "BLOG"]
    if status is not None:
        filters.append(Post.status == status)
    total = await session.scalar(select(func.count()).select_from(Post).where(*filters)) or 0
    rows = list(
        (
            await session.scalars(
                select(Post)
                .where(*filters)
                .order_by(Post.updated_at.desc(), Post.id.desc())
                .offset(page.offset)
                .limit(page.page_size)
            )
        ).all()
    )
    return Page(
        items=[_admin(post) for post in rows],
        page=page.page,
        page_size=page.page_size,
        total=total,
    )


@router.post("", response_model=BlogAdmin, status_code=201)
async def create_blog_post(
    body: BlogCreate,
    tenant: TenantContext = Depends(tenant_context_from_request),
    principal: Principal = Depends(require_permission(Permission.CONTENT_WRITE)),
    session: AsyncSession = Depends(tenant_session),
) -> BlogAdmin:
    try:
        post = await BlogService().create(
            session,
            tenant_id=tenant.tenant_id,
            actor_user_id=principal.user_id,
            body=body,
        )
    except IntegrityError as exc:
        raise ApplicationError(
            "BLOG_POST_CONFLICT", "The blog slug or media relationship conflicts.", status_code=409
        ) from exc
    return _admin(post)


@router.get("/{post_id}", response_model=BlogAdmin)
async def get_blog_post(
    post_id: uuid.UUID,
    _: Principal = Depends(require_permission(Permission.CONTENT_READ)),
    session: AsyncSession = Depends(tenant_session),
) -> BlogAdmin:
    return _admin(await BlogService().get(session, post_id))


@router.patch("/{post_id}", response_model=BlogAdmin)
async def update_blog_post(
    post_id: uuid.UUID,
    body: BlogUpdate,
    tenant: TenantContext = Depends(tenant_context_from_request),
    principal: Principal = Depends(require_permission(Permission.CONTENT_WRITE)),
    session: AsyncSession = Depends(tenant_session),
) -> BlogAdmin:
    service = BlogService()
    post = await service.get(session, post_id, lock=True)
    if post.status == "PUBLISHED":
        _require_publish(principal)
    try:
        await service.update(
            session,
            post=post,
            tenant_id=tenant.tenant_id,
            actor_user_id=principal.user_id,
            body=body,
        )
    except IntegrityError as exc:
        raise ApplicationError(
            "BLOG_POST_CONFLICT", "The blog slug or media relationship conflicts.", status_code=409
        ) from exc
    return _admin(post)


@router.post("/{post_id}/publish", response_model=BlogAdmin)
async def publish_blog_post(
    post_id: uuid.UUID,
    tenant: TenantContext = Depends(tenant_context_from_request),
    principal: Principal = Depends(require_permission(Permission.CONTENT_PUBLISH)),
    session: AsyncSession = Depends(tenant_session),
) -> BlogAdmin:
    service = BlogService()
    post = await service.get(session, post_id, lock=True)
    try:
        await service.publish(
            session,
            post=post,
            tenant_id=tenant.tenant_id,
            actor_user_id=principal.user_id,
        )
    except IntegrityError as exc:
        raise ApplicationError(
            "BLOG_POST_CONFLICT", "The blog slug or media relationship conflicts.", status_code=409
        ) from exc
    return _admin(post)


@router.post("/{post_id}/archive", response_model=BlogAdmin)
async def archive_blog_post(
    post_id: uuid.UUID,
    tenant: TenantContext = Depends(tenant_context_from_request),
    principal: Principal = Depends(require_permission(Permission.CONTENT_PUBLISH)),
    session: AsyncSession = Depends(tenant_session),
) -> BlogAdmin:
    service = BlogService()
    post = await service.get(session, post_id, lock=True)
    await service.archive(
        session,
        post=post,
        tenant_id=tenant.tenant_id,
        actor_user_id=principal.user_id,
    )
    return _admin(post)
