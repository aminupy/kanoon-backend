from __future__ import annotations

import uuid
from collections.abc import Sequence

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.blog.schemas import (
    BlogPublicDetail,
    BlogPublicSummary,
    BlogSnapshot,
    PublicMediaReference,
)
from app.content.models import Post
from app.core.errors import ApplicationError
from app.core.pagination import Page, PageParams
from app.media.models import MediaAsset
from app.site_builds.models import TenantSiteState
from app.tenancy.dependencies import require_feature, tenant_session

router = APIRouter(
    prefix="/api/v1/public/blog",
    tags=["public-blog"],
    dependencies=[Depends(require_feature("blog"))],
)


async def _media_map(
    session: AsyncSession, posts: Sequence[Post]
) -> dict[uuid.UUID, PublicMediaReference]:
    ids = {
        media_id
        for post in posts
        for media_id in (post.cover_image_id, post.og_image_id)
        if media_id is not None
    }
    if not ids:
        return {}
    assets = list(
        (
            await session.scalars(
                select(MediaAsset).where(
                    MediaAsset.id.in_(ids),
                    MediaAsset.status == "READY",
                    MediaAsset.visibility == "PUBLIC",
                )
            )
        ).all()
    )
    return {
        asset.id: PublicMediaReference(
            id=asset.id,
            url=f"/api/v1/public/media/{asset.id}",
            alt_text=asset.alt_text,
            width=asset.width,
            height=asset.height,
        )
        for asset in assets
    }


def _summary(post: Post, media: dict[uuid.UUID, PublicMediaReference]) -> BlogPublicSummary:
    if post.published_at is None:  # pragma: no cover - query invariant
        raise RuntimeError("published post is missing published_at")
    og_image_id = post.og_image_id or post.cover_image_id
    return BlogPublicSummary(
        title=post.title,
        slug=post.slug,
        summary=post.summary,
        cover_image=media.get(post.cover_image_id) if post.cover_image_id else None,
        seo_title=post.seo_title or post.title,
        seo_description=post.seo_description or post.summary,
        og_image=media.get(og_image_id) if og_image_id is not None else None,
        published_at=post.published_at,
        updated_at=post.updated_at,
        locale=post.locale,
    )


def _detail(post: Post, media: dict[uuid.UUID, PublicMediaReference]) -> BlogPublicDetail:
    return BlogPublicDetail(
        **_summary(post, media).model_dump(),
        content_document=post.content_document,
        rendered_html=post.rendered_html or "",
    )


def _published() -> tuple[ColumnElement[bool], ColumnElement[bool], ColumnElement[bool]]:
    return (
        Post.kind == "BLOG",
        Post.status == "PUBLISHED",
        Post.published_at.is_not(None),
    )


@router.get("/snapshot", response_model=BlogSnapshot)
async def blog_snapshot(
    requested_revision: int | None = Query(default=None, ge=0),
    session: AsyncSession = Depends(tenant_session),
) -> BlogSnapshot:
    for _ in range(3):
        before = await session.scalar(select(TenantSiteState.content_revision)) or 0
        posts = list(
            (
                await session.scalars(
                    select(Post)
                    .where(*_published())
                    .order_by(Post.published_at.desc(), Post.id.desc())
                )
            ).all()
        )
        media = await _media_map(session, posts)
        after = await session.scalar(select(TenantSiteState.content_revision)) or 0
        if before == after:
            return BlogSnapshot(
                content_revision=after,
                requested_revision=requested_revision,
                posts=[_detail(post, media) for post in posts],
            )
    raise ApplicationError(
        "SITE_SNAPSHOT_CHANGED",
        "Published content changed while the snapshot was generated; retry the request.",
        status_code=409,
    )


@router.get("", response_model=Page[BlogPublicSummary])
async def list_blog_posts(
    page: PageParams = Depends(), session: AsyncSession = Depends(tenant_session)
) -> Page[BlogPublicSummary]:
    total = await session.scalar(select(func.count()).select_from(Post).where(*_published())) or 0
    posts = list(
        (
            await session.scalars(
                select(Post)
                .where(*_published())
                .order_by(Post.published_at.desc(), Post.id.desc())
                .offset(page.offset)
                .limit(page.page_size)
            )
        ).all()
    )
    media = await _media_map(session, posts)
    return Page(
        items=[_summary(post, media) for post in posts],
        page=page.page,
        page_size=page.page_size,
        total=total,
    )


@router.get("/{slug}", response_model=BlogPublicDetail)
async def get_blog_post(
    slug: str, session: AsyncSession = Depends(tenant_session)
) -> BlogPublicDetail:
    post = await session.scalar(select(Post).where(*_published(), Post.slug == slug))
    if post is None:
        raise ApplicationError("BLOG_POST_NOT_FOUND", "Blog post was not found.", status_code=404)
    return _detail(post, await _media_map(session, [post]))
