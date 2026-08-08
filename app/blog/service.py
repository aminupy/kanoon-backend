from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.blog.rich_text import referenced_media_ids, render_document, validate_document
from app.blog.schemas import BlogCreate, BlogUpdate
from app.content.models import Post, PostMediaReference
from app.core.errors import ApplicationError
from app.media.models import MediaAsset
from app.site_builds.service import SiteBuildService

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class BlogService:
    async def get(self, session: AsyncSession, post_id: uuid.UUID, *, lock: bool = False) -> Post:
        statement = select(Post).where(Post.id == post_id, Post.kind == "BLOG")
        if lock:
            statement = statement.with_for_update()
        post = await session.scalar(statement)
        if post is None:
            raise ApplicationError(
                "BLOG_POST_NOT_FOUND", "Blog post was not found.", status_code=404
            )
        return post

    async def create(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        body: BlogCreate,
    ) -> Post:
        values = body.model_dump()
        document = validate_document(values.pop("content_document"))
        await self._validate_media(session, tenant_id, self._all_media_ids(values, document))
        post = Post(
            tenant_id=tenant_id,
            kind="BLOG",
            status="DRAFT",
            body="",
            content_document=document,
            rendered_html=render_document(document),
            created_by=actor_user_id,
            updated_by=actor_user_id,
            **values,
        )
        session.add(post)
        await session.flush()
        await self._sync_references(session, post, document)
        self._audit(session, post, actor_user_id, "blog_post.created")
        return post

    async def update(
        self,
        session: AsyncSession,
        *,
        post: Post,
        tenant_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        body: BlogUpdate,
    ) -> tuple[Post, bool]:
        updates = body.model_dump(exclude_unset=True)
        if "content_document" in updates and updates["content_document"] is None:
            raise ApplicationError(
                "BLOG_DOCUMENT_INVALID", "Blog content cannot be null.", status_code=422
            )
        changed = False
        for field, value in updates.items():
            if getattr(post, field) != value:
                setattr(post, field, value)
                changed = True
        if not changed:
            return post, False
        document = validate_document(
            post.content_document, require_content=post.status == "PUBLISHED"
        )
        await self._validate_media(
            session,
            tenant_id,
            self._all_media_ids(
                {
                    "cover_image_id": post.cover_image_id,
                    "og_image_id": post.og_image_id,
                },
                document,
            ),
            public=post.status == "PUBLISHED",
        )
        post.rendered_html = render_document(document)
        post.updated_by = actor_user_id
        await session.flush()
        await self._sync_references(session, post, document)
        if post.status == "PUBLISHED":
            await SiteBuildService().public_content_changed(
                session,
                tenant_id=tenant_id,
                reason="published_blog_updated",
                entity_type="blog_post",
                entity_id=post.id,
                created_by=actor_user_id,
            )
            self._audit(session, post, actor_user_id, "blog_post.published_updated")
        await session.refresh(post)
        return post, True

    async def publish(
        self,
        session: AsyncSession,
        *,
        post: Post,
        tenant_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> Post:
        if post.status == "PUBLISHED":
            return post
        if not post.title.strip() or not SLUG_PATTERN.fullmatch(post.slug):
            raise ApplicationError(
                "BLOG_PUBLISH_INVALID",
                "Title and slug are required for publication.",
                status_code=422,
            )
        document = validate_document(post.content_document, require_content=True)
        await self._validate_media(
            session,
            tenant_id,
            self._all_media_ids(
                {"cover_image_id": post.cover_image_id, "og_image_id": post.og_image_id},
                document,
            ),
            public=True,
        )
        post.rendered_html = render_document(document)
        post.status = "PUBLISHED"
        post.published_at = datetime.now(UTC)
        post.updated_by = actor_user_id
        await session.flush()
        await self._sync_references(session, post, document)
        await SiteBuildService().public_content_changed(
            session,
            tenant_id=tenant_id,
            reason="blog_published",
            entity_type="blog_post",
            entity_id=post.id,
            created_by=actor_user_id,
        )
        self._audit(session, post, actor_user_id, "blog_post.published")
        await session.refresh(post)
        return post

    async def archive(
        self,
        session: AsyncSession,
        *,
        post: Post,
        tenant_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> Post:
        if post.status == "ARCHIVED":
            return post
        was_published = post.status == "PUBLISHED"
        post.status = "ARCHIVED"
        post.updated_by = actor_user_id
        await session.flush()
        if was_published:
            await SiteBuildService().public_content_changed(
                session,
                tenant_id=tenant_id,
                reason="blog_archived",
                entity_type="blog_post",
                entity_id=post.id,
                created_by=actor_user_id,
            )
        self._audit(session, post, actor_user_id, "blog_post.archived")
        await session.refresh(post)
        return post

    def _all_media_ids(self, values: dict[str, Any], document: dict[str, Any]) -> set[uuid.UUID]:
        result = referenced_media_ids(document)
        result.update(
            value
            for name in ("cover_image_id", "og_image_id")
            if (value := values.get(name)) is not None
        )
        return result

    async def _validate_media(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        media_ids: set[uuid.UUID],
        *,
        public: bool = False,
    ) -> None:
        for media_id in media_ids:
            media = await session.scalar(
                select(MediaAsset).where(
                    MediaAsset.id == media_id, MediaAsset.tenant_id == tenant_id
                )
            )
            if media is None:
                raise ApplicationError(
                    "BLOG_MEDIA_NOT_FOUND",
                    "A referenced media asset was not found for this site.",
                    status_code=422,
                )
            if public and (media.status != "READY" or media.visibility != "PUBLIC"):
                raise ApplicationError(
                    "BLOG_MEDIA_NOT_PUBLIC",
                    "Published blog media must be ready and public.",
                    status_code=422,
                )

    async def _sync_references(
        self, session: AsyncSession, post: Post, document: dict[str, Any]
    ) -> None:
        await session.execute(
            delete(PostMediaReference).where(PostMediaReference.post_id == post.id)
        )
        session.add_all(
            PostMediaReference(tenant_id=post.tenant_id, post_id=post.id, media_id=media_id)
            for media_id in referenced_media_ids(document)
        )
        await session.flush()

    def _audit(
        self, session: AsyncSession, post: Post, actor_user_id: uuid.UUID, action: str
    ) -> None:
        session.add(
            AuditEvent(
                tenant_id=post.tenant_id,
                actor_user_id=actor_user_id,
                action=action,
                entity_type="blog_post",
                entity_id=post.id,
                metadata_={},
                created_at=datetime.now(UTC),
            )
        )
