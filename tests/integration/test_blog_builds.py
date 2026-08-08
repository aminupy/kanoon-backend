from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from app.auth.models import TenantMembership, User
from app.auth.security import create_access_token
from app.blog.schemas import BlogCreate, BlogUpdate
from app.blog.service import BlogService
from app.content.models import Post
from app.core.config import Settings
from app.core.database import Database
from app.core.errors import ApplicationError
from app.main import create_app
from app.media.models import MediaAsset
from app.site_builds.executor import FakeSiteBuildExecutor
from app.site_builds.models import SiteBuildRequest, TenantSiteBuildConfig, TenantSiteState
from app.site_builds.result_service import BuildResultService
from app.site_builds.schemas import BuildResult
from app.site_builds.service import SiteBuildService
from app.site_builds.signing import sign_message
from app.site_builds.worker import SiteBuildWorker
from app.tenancy.models import Tenant, TenantDomain, TenantFeature

pytestmark = pytest.mark.integration


def document(
    text: str = "Published content", media_id: uuid.UUID | None = None
) -> dict[str, object]:
    content: list[dict[str, object]] = [
        {"type": "paragraph", "content": [{"type": "text", "text": text}]}
    ]
    if media_id is not None:
        content.append({"type": "image", "attrs": {"media_id": str(media_id), "alt": "Image"}})
    return {"type": "doc", "content": content}


@pytest.fixture
async def blog_tenants(
    owner_engine: AsyncEngine,
) -> dict[str, uuid.UUID | str]:
    tenant_a, tenant_b, user_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    media_a, media_b = uuid.uuid4(), uuid.uuid4()
    host_a = f"blog-a-{tenant_a}.example.test"
    host_b = f"blog-b-{tenant_b}.example.test"
    now = datetime.now(UTC)
    async with owner_engine.begin() as connection:
        await connection.execute(
            insert(Tenant),
            [
                {
                    "id": tenant_a,
                    "name": "Blog A",
                    "slug": f"blog-a-{tenant_a}",
                    "status": "ACTIVE",
                    "default_locale": "fa-IR",
                    "timezone": "Asia/Tehran",
                    "default_currency": "IRR",
                },
                {
                    "id": tenant_b,
                    "name": "Blog B",
                    "slug": f"blog-b-{tenant_b}",
                    "status": "ACTIVE",
                    "default_locale": "fa-IR",
                    "timezone": "Asia/Tehran",
                    "default_currency": "IRR",
                },
            ],
        )
        await connection.execute(
            insert(User),
            {
                "id": user_id,
                "email": f"blog-{user_id}@example.test",
                "password_hash": "unused",
                "is_active": True,
                "is_platform_admin": False,
            },
        )
        await connection.execute(
            insert(TenantDomain),
            [
                {
                    "tenant_id": tenant_a,
                    "hostname": host_a,
                    "is_primary": True,
                    "is_active": True,
                    "created_at": now,
                },
                {
                    "tenant_id": tenant_b,
                    "hostname": host_b,
                    "is_primary": True,
                    "is_active": True,
                    "created_at": now,
                },
            ],
        )
        await connection.execute(
            insert(TenantFeature),
            [
                {
                    "tenant_id": tenant_a,
                    "feature_key": "blog",
                    "enabled": True,
                    "configuration": {},
                },
                {
                    "tenant_id": tenant_b,
                    "feature_key": "blog",
                    "enabled": True,
                    "configuration": {},
                },
            ],
        )
        await connection.execute(
            insert(TenantMembership),
            [
                {
                    "tenant_id": tenant_a,
                    "user_id": user_id,
                    "role": "TENANT_ADMIN",
                    "created_at": now,
                },
                {
                    "tenant_id": tenant_b,
                    "user_id": user_id,
                    "role": "TENANT_ADMIN",
                    "created_at": now,
                },
            ],
        )
        await connection.execute(
            insert(MediaAsset),
            [
                {
                    "id": media_a,
                    "tenant_id": tenant_a,
                    "object_key": f"tenants/{tenant_a}/a.jpg",
                    "original_filename": "a.jpg",
                    "mime_type": "image/jpeg",
                    "size_bytes": 100,
                    "status": "READY",
                    "visibility": "PUBLIC",
                },
                {
                    "id": media_b,
                    "tenant_id": tenant_b,
                    "object_key": f"tenants/{tenant_b}/b.jpg",
                    "original_filename": "b.jpg",
                    "mime_type": "image/jpeg",
                    "size_bytes": 100,
                    "status": "READY",
                    "visibility": "PUBLIC",
                },
            ],
        )
    return {
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "user": user_id,
        "media_a": media_a,
        "media_b": media_b,
        "host_a": host_a,
        "host_b": host_b,
    }


async def create_draft(
    database: Database,
    values: dict[str, uuid.UUID | str],
    *,
    tenant_key: str = "tenant_a",
    slug: str = "post",
) -> uuid.UUID:
    tenant_id = values[tenant_key]
    user_id = values["user"]
    assert isinstance(tenant_id, uuid.UUID) and isinstance(user_id, uuid.UUID)
    async with database.tenant_session(tenant_id) as session:
        post = await BlogService().create(
            session,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            body=BlogCreate(title="Draft post", slug=slug, content_document=document()),
        )
        return post.id


async def test_draft_changes_and_upload_do_not_build_but_public_changes_coalesce(
    database: Database, blog_tenants: dict[str, uuid.UUID | str]
) -> None:
    tenant_id = blog_tenants["tenant_a"]
    user_id = blog_tenants["user"]
    assert isinstance(tenant_id, uuid.UUID) and isinstance(user_id, uuid.UUID)
    post_id = await create_draft(database, blog_tenants)
    async with database.tenant_session(tenant_id) as session:
        assert await session.scalar(select(func.count()).select_from(SiteBuildRequest)) == 0
        post = await BlogService().get(session, post_id, lock=True)
        await BlogService().update(
            session,
            post=post,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            body=BlogUpdate(title="Autosaved draft"),
        )
        session.add(
            MediaAsset(
                tenant_id=tenant_id,
                object_key=f"tenants/{tenant_id}/{uuid.uuid4()}.jpg",
                original_filename="draft.jpg",
                mime_type="image/jpeg",
                size_bytes=1,
                status="PENDING",
                visibility="PRIVATE",
            )
        )
    async with database.tenant_session(tenant_id) as session:
        assert await session.scalar(select(func.count()).select_from(SiteBuildRequest)) == 0
        post = await BlogService().get(session, post_id, lock=True)
        await BlogService().publish(session, post=post, tenant_id=tenant_id, actor_user_id=user_id)
    async with database.tenant_session(tenant_id) as session:
        first = await session.scalar(select(SiteBuildRequest))
        state = await session.get(TenantSiteState, tenant_id)
        assert first is not None and first.target_revision == 1 and first.status == "PENDING"
        assert state is not None and state.content_revision == 1
        first_id = first.id
        post = await BlogService().get(session, post_id, lock=True)
        await BlogService().update(
            session,
            post=post,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            body=BlogUpdate(content_document=document("Updated public content")),
        )
    async with database.tenant_session(tenant_id) as session:
        request = await session.scalar(select(SiteBuildRequest))
        assert request is not None and request.id == first_id and request.target_revision == 2
        post = await BlogService().get(session, post_id, lock=True)
        await BlogService().archive(session, post=post, tenant_id=tenant_id, actor_user_id=user_id)
    async with database.tenant_session(tenant_id) as session:
        request = await session.scalar(select(SiteBuildRequest))
        assert request is not None and request.id == first_id and request.target_revision == 3


async def test_cross_tenant_and_missing_media_are_rejected(
    database: Database, blog_tenants: dict[str, uuid.UUID | str]
) -> None:
    tenant_a = blog_tenants["tenant_a"]
    user_id = blog_tenants["user"]
    media_b = blog_tenants["media_b"]
    assert all(isinstance(value, uuid.UUID) for value in (tenant_a, user_id, media_b))
    assert isinstance(tenant_a, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    assert isinstance(media_b, uuid.UUID)
    for media_id in (media_b, uuid.uuid4()):
        with pytest.raises(ApplicationError) as error:
            async with database.tenant_session(tenant_a) as session:
                await BlogService().create(
                    session,
                    tenant_id=tenant_a,
                    actor_user_id=user_id,
                    body=BlogCreate(
                        title="Invalid media",
                        slug=f"invalid-{media_id.hex}",
                        content_document=document(media_id=media_id),
                    ),
                )
        assert error.value.code == "BLOG_MEDIA_NOT_FOUND"


async def test_publish_accepts_tenant_media_and_rechecks_missing_document_media(
    database: Database, blog_tenants: dict[str, uuid.UUID | str]
) -> None:
    tenant_id = blog_tenants["tenant_a"]
    user_id = blog_tenants["user"]
    media_id = blog_tenants["media_a"]
    assert isinstance(tenant_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    assert isinstance(media_id, uuid.UUID)
    async with database.tenant_session(tenant_id) as session:
        valid = await BlogService().create(
            session,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            body=BlogCreate(
                title="Valid image",
                slug="valid-image",
                content_document=document(media_id=media_id),
            ),
        )
        await BlogService().publish(session, post=valid, tenant_id=tenant_id, actor_user_id=user_id)
        assert valid.status == "PUBLISHED"
    missing_id = uuid.uuid4()
    invalid_id = await create_draft(database, blog_tenants, slug="missing-at-publish")
    async with database.tenant_session(tenant_id) as session:
        invalid = await BlogService().get(session, invalid_id, lock=True)
        invalid.content_document = document(media_id=missing_id)
    with pytest.raises(ApplicationError) as error:
        async with database.tenant_session(tenant_id) as session:
            invalid = await BlogService().get(session, invalid_id, lock=True)
            await BlogService().publish(
                session, post=invalid, tenant_id=tenant_id, actor_user_id=user_id
            )
    assert error.value.code == "BLOG_MEDIA_NOT_FOUND"


async def test_admin_blog_rows_are_tenant_isolated(
    database: Database, blog_tenants: dict[str, uuid.UUID | str]
) -> None:
    draft_a = await create_draft(database, blog_tenants, tenant_key="tenant_a", slug="draft-a")
    draft_b = await create_draft(database, blog_tenants, tenant_key="tenant_b", slug="draft-b")
    tenant_a = blog_tenants["tenant_a"]
    tenant_b = blog_tenants["tenant_b"]
    assert isinstance(tenant_a, uuid.UUID) and isinstance(tenant_b, uuid.UUID)
    async with database.tenant_session(tenant_a) as session:
        ids = set((await session.scalars(select(Post.id).where(Post.kind == "BLOG"))).all())
        assert draft_a in ids and draft_b not in ids
        with pytest.raises(ApplicationError):
            await BlogService().get(session, draft_b)
    async with database.tenant_session(tenant_b) as session:
        ids = set((await session.scalars(select(Post.id).where(Post.kind == "BLOG"))).all())
        assert draft_b in ids and draft_a not in ids


async def test_running_build_gets_followup_and_stale_result_cannot_mark_newer_deployed(
    database: Database,
    settings: Settings,
    blog_tenants: dict[str, uuid.UUID | str],
) -> None:
    tenant_id = blog_tenants["tenant_a"]
    user_id = blog_tenants["user"]
    assert isinstance(tenant_id, uuid.UUID) and isinstance(user_id, uuid.UUID)
    async with database.tenant_session(tenant_id) as session:
        running = await SiteBuildService().public_content_changed(
            session,
            tenant_id=tenant_id,
            reason="first",
            entity_type="blog_post",
            entity_id=uuid.uuid4(),
            created_by=user_id,
        )
        running.status = "RUNNING"
        running.attempt_count = 1
        running_id = running.id
    async with database.tenant_session(tenant_id) as session:
        followup = await SiteBuildService().public_content_changed(
            session,
            tenant_id=tenant_id,
            reason="changed_while_running",
            entity_type="blog_post",
            entity_id=uuid.uuid4(),
            created_by=user_id,
        )
        assert followup.id != running_id and followup.target_revision == 2
        followup_id = followup.id
    success = BuildResult(tenant_id=tenant_id, status="SUCCESSFUL", actual_revision=1)
    async with database.tenant_session(tenant_id) as session:
        recorded = await BuildResultService(settings).record(
            session, request_id=running_id, result=success
        )
        assert recorded.status == "SUCCESSFUL"
    async with database.tenant_session(tenant_id) as session:
        duplicate = await BuildResultService(settings).record(
            session, request_id=running_id, result=success
        )
        state = await session.get(TenantSiteState, tenant_id)
        assert duplicate.status == "SUCCESSFUL"
        assert state is not None
        assert state.content_revision == 2
        assert state.last_successful_build_revision == 1
        managed_followup = await session.get(SiteBuildRequest, followup_id, with_for_update=True)
        assert managed_followup is not None
        managed_followup.status = "RUNNING"
        managed_followup.attempt_count = settings.site_build_max_attempts
    async with database.tenant_session(tenant_id) as session:
        await BuildResultService(settings).record(
            session,
            request_id=followup_id,
            result=BuildResult(
                tenant_id=tenant_id,
                status="FAILED",
                error="sanitized failure",
                retryable=False,
            ),
        )
        state = await session.get(TenantSiteState, tenant_id)
        assert state is not None and state.last_successful_build_revision == 1


async def test_rapid_requests_coalesce_per_tenant_and_rls_keeps_tenants_independent(
    database: Database, blog_tenants: dict[str, uuid.UUID | str]
) -> None:
    tenant_a = blog_tenants["tenant_a"]
    tenant_b = blog_tenants["tenant_b"]
    user_id = blog_tenants["user"]
    assert isinstance(tenant_a, uuid.UUID)
    assert isinstance(tenant_b, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)

    async def change(tenant_id: uuid.UUID, reason: str) -> None:
        async with database.tenant_session(tenant_id) as session:
            await SiteBuildService().public_content_changed(
                session,
                tenant_id=tenant_id,
                reason=reason,
                entity_type="blog_post",
                entity_id=uuid.uuid4(),
                created_by=user_id,
            )

    await asyncio.gather(change(tenant_a, "a1"), change(tenant_a, "a2"), change(tenant_b, "b1"))
    async with database.tenant_session(tenant_a) as session:
        requests_a = list((await session.scalars(select(SiteBuildRequest))).all())
        assert len(requests_a) == 1 and requests_a[0].target_revision == 2
    async with database.tenant_session(tenant_b) as session:
        requests_b = list((await session.scalars(select(SiteBuildRequest))).all())
        assert len(requests_b) == 1 and requests_b[0].target_revision == 1
        assert requests_b[0].id != requests_a[0].id


async def test_worker_claims_under_tenant_rls_and_uses_fake_executor(
    database: Database,
    settings: Settings,
    owner_engine: AsyncEngine,
    blog_tenants: dict[str, uuid.UUID | str],
) -> None:
    tenant_id = blog_tenants["tenant_a"]
    user_id = blog_tenants["user"]
    host = blog_tenants["host_a"]
    assert isinstance(tenant_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    assert isinstance(host, str)
    async with owner_engine.begin() as connection:
        await connection.execute(update(TenantSiteBuildConfig).values(enabled=False))
    async with database.tenant_session(tenant_id) as session:
        session.add(
            TenantSiteBuildConfig(
                tenant_id=tenant_id,
                enabled=True,
                canonical_domain=host,
                build_target_key="astro-a",
                deployment_target_key="nginx-a",
            )
        )
        request = await SiteBuildService().public_content_changed(
            session,
            tenant_id=tenant_id,
            reason="publish",
            entity_type="blog_post",
            entity_id=uuid.uuid4(),
            created_by=user_id,
        )
        request_id = request.id
    fake = FakeSiteBuildExecutor()
    worker = SiteBuildWorker(database, settings, fake)
    assert await worker.run_once() == 1
    assert len(fake.triggered) == 1
    assert fake.triggered[0].tenant_id == tenant_id
    assert fake.triggered[0].build_request_id == request_id
    assert fake.triggered[0].target_revision == 1
    async with database.tenant_session(tenant_id) as session:
        claimed = await session.get(SiteBuildRequest, request_id)
        assert claimed is not None and claimed.status == "RUNNING"


async def test_public_domains_cannot_cross_retrieve_same_slug(
    database: Database,
    settings: Settings,
    blog_tenants: dict[str, uuid.UUID | str],
) -> None:
    tenant_a = blog_tenants["tenant_a"]
    tenant_b = blog_tenants["tenant_b"]
    user_id = blog_tenants["user"]
    assert isinstance(tenant_a, uuid.UUID)
    assert isinstance(tenant_b, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    for tenant_id, title in ((tenant_a, "Tenant A post"), (tenant_b, "Tenant B post")):
        async with database.tenant_session(tenant_id) as session:
            post = await BlogService().create(
                session,
                tenant_id=tenant_id,
                actor_user_id=user_id,
                body=BlogCreate(title=title, slug="same-slug", content_document=document(title)),
            )
            await BlogService().publish(
                session, post=post, tenant_id=tenant_id, actor_user_id=user_id
            )
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response_a = await client.get(
            "/api/v1/public/blog/same-slug", headers={"Host": str(blog_tenants["host_a"])}
        )
        response_b = await client.get(
            "/api/v1/public/blog/same-slug", headers={"Host": str(blog_tenants["host_b"])}
        )
        snapshot = await client.get(
            "/api/v1/public/blog/snapshot?requested_revision=0",
            headers={"Host": str(blog_tenants["host_a"])},
        )
        async with database.tenant_session(tenant_b) as session:
            feature = await session.get(TenantFeature, (tenant_b, "blog"), with_for_update=True)
            assert feature is not None
            feature.enabled = False
        disabled = await client.get(
            "/api/v1/public/blog", headers={"Host": str(blog_tenants["host_b"])}
        )
    assert response_a.status_code == response_b.status_code == 200
    assert response_a.json()["title"] == "Tenant A post"
    assert response_b.json()["title"] == "Tenant B post"
    assert snapshot.status_code == 200
    assert snapshot.json()["content_revision"] == 1
    assert snapshot.json()["requested_revision"] == 0
    assert disabled.status_code == 404
    await app.state.database.dispose()


async def test_admin_http_draft_publish_integration(
    database: Database,
    settings: Settings,
    blog_tenants: dict[str, uuid.UUID | str],
) -> None:
    tenant_id = blog_tenants["tenant_a"]
    user_id = blog_tenants["user"]
    host = blog_tenants["host_a"]
    assert isinstance(tenant_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    assert isinstance(host, str)
    token, _ = create_access_token(
        settings, user_id=user_id, tenant_id=tenant_id, is_platform_admin=False
    )
    headers = {"Host": host, "Authorization": f"Bearer {token}"}
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/v1/admin/blog",
            headers=headers,
            json={"title": "HTTP draft", "slug": "http-draft", "content_document": document()},
        )
        assert created.status_code == 201
        post_id = created.json()["id"]
        assert created.json()["status"] == "DRAFT"
        patched = await client.patch(
            f"/api/v1/admin/blog/{post_id}",
            headers=headers,
            json={"title": "HTTP draft edited"},
        )
        assert patched.status_code == 200
        async with database.tenant_session(tenant_id) as session:
            assert await session.scalar(select(func.count()).select_from(SiteBuildRequest)) == 0
        published = await client.post(f"/api/v1/admin/blog/{post_id}/publish", headers=headers)
        assert published.status_code == 200
        assert published.json()["status"] == "PUBLISHED"
    async with database.tenant_session(tenant_id) as session:
        request = await session.scalar(select(SiteBuildRequest))
        assert request is not None and request.target_revision == 1
    await app.state.database.dispose()


async def test_worker_retries_transient_trigger_failure(
    database: Database,
    settings: Settings,
    owner_engine: AsyncEngine,
    blog_tenants: dict[str, uuid.UUID | str],
) -> None:
    tenant_id = blog_tenants["tenant_a"]
    user_id = blog_tenants["user"]
    host = blog_tenants["host_a"]
    assert isinstance(tenant_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    assert isinstance(host, str)
    async with owner_engine.begin() as connection:
        await connection.execute(update(TenantSiteBuildConfig).values(enabled=False))
    async with database.tenant_session(tenant_id) as session:
        session.add(
            TenantSiteBuildConfig(
                tenant_id=tenant_id,
                enabled=True,
                canonical_domain=host,
                build_target_key="retry-target",
                deployment_target_key="retry-deploy",
            )
        )
        build = await SiteBuildService().public_content_changed(
            session,
            tenant_id=tenant_id,
            reason="retry_test",
            entity_type="blog_post",
            entity_id=uuid.uuid4(),
            created_by=user_id,
        )
        build_id = build.id
    fake = FakeSiteBuildExecutor(failures=1)
    worker = SiteBuildWorker(database, settings, fake)
    await worker.run_once()
    async with database.tenant_session(tenant_id) as session:
        retry = await session.get(SiteBuildRequest, build_id, with_for_update=True)
        assert retry is not None and retry.status == "PENDING" and retry.attempt_count == 1
        retry.next_attempt_at = datetime.now(UTC)
    await worker.run_once()
    async with database.tenant_session(tenant_id) as session:
        running = await session.get(SiteBuildRequest, build_id)
        assert running is not None and running.status == "RUNNING"
        assert running.attempt_count == 2
    assert len(fake.triggered) == 2


async def test_authenticated_result_callback_is_replay_safe(
    database: Database,
    settings: Settings,
    blog_tenants: dict[str, uuid.UUID | str],
) -> None:
    tenant_id = blog_tenants["tenant_a"]
    user_id = blog_tenants["user"]
    assert isinstance(tenant_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    async with database.tenant_session(tenant_id) as session:
        build = await SiteBuildService().public_content_changed(
            session,
            tenant_id=tenant_id,
            reason="callback_test",
            entity_type="blog_post",
            entity_id=uuid.uuid4(),
            created_by=user_id,
        )
        build.status = "RUNNING"
        build.attempt_count = 1
        build_id = build.id
    payload = {
        "tenant_id": str(tenant_id),
        "status": "SUCCESSFUL",
        "actual_revision": 1,
        "retryable": True,
    }
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    path = f"/api/v1/internal/site-builds/{build_id}/result"
    timestamp = int(time.time())
    signature = sign_message(
        settings.site_build_hmac_secret.get_secret_value(), timestamp, "POST", path, body
    )
    headers = {
        "Content-Type": "application/json",
        "X-Kanoon-Timestamp": str(timestamp),
        "X-Kanoon-Signature": signature,
    }
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://internal") as client:
        first = await client.post(path, content=body, headers=headers)
        duplicate = await client.post(path, content=body, headers=headers)
        rejected = await client.post(
            path, content=body, headers={**headers, "X-Kanoon-Signature": "0" * 64}
        )
    assert first.status_code == duplicate.status_code == 200
    assert rejected.status_code == 401
    async with database.tenant_session(tenant_id) as session:
        state = await session.get(TenantSiteState, tenant_id)
        recorded_build = await session.get(SiteBuildRequest, build_id)
        assert state is not None and state.last_successful_build_revision == 1
        assert recorded_build is not None and recorded_build.status == "SUCCESSFUL"
    await app.state.database.dispose()
