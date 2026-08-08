from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.content.models import Post
from app.core.database import Database
from app.exams.models import ExamOffering, ExamPricingPlan, PricingPlan
from app.media.models import MediaAsset
from app.tenancy.models import Tenant

pytestmark = pytest.mark.integration


@pytest.fixture
async def tenant_rows(
    owner_engine: AsyncEngine,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    media_a, media_b = uuid.uuid4(), uuid.uuid4()
    async with owner_engine.begin() as connection:
        await connection.execute(
            insert(Tenant),
            [
                {
                    "id": tenant_a,
                    "name": "Tenant A",
                    "slug": f"a-{tenant_a}",
                    "status": "ACTIVE",
                    "default_locale": "fa-IR",
                    "timezone": "Asia/Tehran",
                    "default_currency": "IRR",
                },
                {
                    "id": tenant_b,
                    "name": "Tenant B",
                    "slug": f"b-{tenant_b}",
                    "status": "ACTIVE",
                    "default_locale": "fa-IR",
                    "timezone": "Asia/Tehran",
                    "default_currency": "IRR",
                },
            ],
        )
        await connection.execute(
            insert(MediaAsset),
            [
                {
                    "id": media_a,
                    "tenant_id": tenant_a,
                    "object_key": f"{tenant_a}/a.jpg",
                    "original_filename": "a.jpg",
                    "mime_type": "image/jpeg",
                    "size_bytes": 1,
                    "status": "READY",
                },
                {
                    "id": media_b,
                    "tenant_id": tenant_b,
                    "object_key": f"{tenant_b}/b.jpg",
                    "original_filename": "b.jpg",
                    "mime_type": "image/jpeg",
                    "size_bytes": 1,
                    "status": "READY",
                },
            ],
        )
        await connection.execute(
            insert(Post),
            [
                {
                    "id": uuid.uuid4(),
                    "tenant_id": tenant_a,
                    "kind": "NEWS",
                    "title": "A only",
                    "slug": "a-only",
                    "body": "secret-a",
                    "status": "PUBLISHED",
                },
                {
                    "id": uuid.uuid4(),
                    "tenant_id": tenant_b,
                    "kind": "NEWS",
                    "title": "B only",
                    "slug": "b-only",
                    "body": "secret-b",
                    "status": "PUBLISHED",
                },
            ],
        )
    return tenant_a, tenant_b, media_a, media_b


async def test_reads_are_isolated_and_absent_context_fails_closed(
    database: Database, tenant_rows: tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]
) -> None:
    tenant_a, tenant_b, _, _ = tenant_rows
    async with database.tenant_session(tenant_a) as session:
        titles = (await session.scalars(select(Post.title))).all()
        assert titles == ["A only"]
    async with database.tenant_session(tenant_b) as session:
        titles = (await session.scalars(select(Post.title))).all()
        assert titles == ["B only"]
    async with database.global_session() as session:
        assert (await session.scalars(select(Post.title))).all() == []


async def test_update_and_delete_cannot_touch_another_tenant(
    database: Database, tenant_rows: tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]
) -> None:
    tenant_a, tenant_b, _, _ = tenant_rows
    async with database.tenant_session(tenant_a) as session:
        updated = await session.scalars(
            update(Post).where(Post.tenant_id == tenant_b).values(title="leaked").returning(Post.id)
        )
        deleted = await session.scalars(
            delete(Post).where(Post.tenant_id == tenant_b).returning(Post.id)
        )
        assert updated.all() == []
        assert deleted.all() == []
    async with database.tenant_session(tenant_b) as session:
        assert (await session.scalar(select(Post.title))) == "B only"


async def test_cross_tenant_media_reference_is_rejected(
    database: Database, tenant_rows: tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]
) -> None:
    tenant_a, _, _, media_b = tenant_rows
    with pytest.raises(IntegrityError):
        async with database.tenant_session(tenant_a) as session:
            session.add(
                Post(
                    tenant_id=tenant_a,
                    kind="NEWS",
                    title="Invalid cover",
                    slug="invalid-cover",
                    body="body",
                    cover_image_id=media_b,
                    status="DRAFT",
                )
            )
            await session.flush()


async def test_cross_tenant_exam_pricing_reference_is_rejected(
    database: Database, tenant_rows: tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]
) -> None:
    tenant_a, tenant_b, _, _ = tenant_rows
    exam_id, plan_id = uuid.uuid4(), uuid.uuid4()
    async with database.tenant_session(tenant_a) as session:
        session.add(
            ExamOffering(
                id=exam_id,
                tenant_id=tenant_a,
                title="Exam A",
                slug="exam-a",
                description="A",
                mode="ONLINE",
                status="DRAFT",
            )
        )
        await session.flush()
    async with database.tenant_session(tenant_b) as session:
        session.add(
            PricingPlan(
                id=plan_id,
                tenant_id=tenant_b,
                title="Plan B",
                slug="plan-b",
                description="B",
                mode="ONLINE",
                amount=10,
                currency="IRR",
                status="DRAFT",
            )
        )
        await session.flush()
    with pytest.raises(IntegrityError):
        async with database.tenant_session(tenant_a) as session:
            session.add(
                ExamPricingPlan(
                    tenant_id=tenant_a,
                    exam_offering_id=exam_id,
                    pricing_plan_id=plan_id,
                )
            )
            await session.flush()


async def test_transaction_local_context_does_not_leak_through_pool(
    database: Database, tenant_rows: tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]
) -> None:
    tenant_a, tenant_b, _, _ = tenant_rows
    async with database.tenant_session(tenant_a) as session:
        assert (await session.scalar(select(Post.title))) == "A only"
        setting = await session.scalar(text("SELECT current_setting('app.current_tenant_id')"))
        assert setting == str(tenant_a)
    async with database.global_session() as session:
        setting = await session.scalar(
            text("SELECT NULLIF(current_setting('app.current_tenant_id', true), '')")
        )
        assert setting is None
        assert (await session.scalars(select(Post))).all() == []
    async with database.tenant_session(tenant_b) as session:
        assert (await session.scalar(select(Post.title))) == "B only"
