from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from pydantic import BaseModel
from sqlalchemy import insert, inspect
from sqlalchemy.ext.asyncio import AsyncEngine

from app.auth.models import User
from app.content.admin_schemas import (
    BannerAdmin,
    ExamOfferingAdmin,
    ExamOfferingWrite,
    GalleryAlbumAdmin,
    GalleryAlbumWrite,
    HonorAdmin,
    HonorCategoryAdmin,
    HonorCategoryWrite,
    HonorWrite,
    PostAdmin,
    PricingPlanAdmin,
    PricingPlanWrite,
    SampleExamAdmin,
    SampleExamWrite,
    StaffAdmin,
    StaffWrite,
)
from app.content.admin_service import AdminContentService
from app.content.models import (
    Banner,
    GalleryAlbum,
    Honor,
    HonorCategory,
    Post,
    SampleExam,
    StaffMember,
)
from app.content.schemas import BannerWrite, PostWrite
from app.core.config import Settings
from app.core.database import Database
from app.core.models import Base
from app.exams.models import ExamOffering, PricingPlan
from app.media.models import MediaAsset
from app.registrations.models import Registration
from app.registrations.schemas import RegistrationPatch, RegistrationResponse
from app.registrations.service import RegistrationService
from app.tenancy.models import Tenant

pytestmark = pytest.mark.integration


@pytest.fixture
async def update_context(owner_engine: AsyncEngine) -> dict[str, uuid.UUID]:
    values = {
        "tenant": uuid.uuid4(),
        "actor": uuid.uuid4(),
        "media": uuid.uuid4(),
        "category": uuid.uuid4(),
        "plan": uuid.uuid4(),
        "exam": uuid.uuid4(),
    }
    async with owner_engine.begin() as connection:
        await connection.execute(
            insert(Tenant),
            {
                "id": values["tenant"],
                "name": "Update lifecycle tenant",
                "slug": f"update-{values['tenant']}",
                "status": "ACTIVE",
                "default_locale": "fa-IR",
                "timezone": "Asia/Tehran",
                "default_currency": "IRR",
            },
        )
        await connection.execute(
            insert(User),
            {
                "id": values["actor"],
                "email": f"update-{values['actor']}@example.test",
                "password_hash": "!",
                "is_active": True,
                "is_platform_admin": False,
            },
        )
        await connection.execute(
            insert(MediaAsset),
            {
                "id": values["media"],
                "tenant_id": values["tenant"],
                "object_key": f"tenants/{values['tenant']}/update-fixture.png",
                "original_filename": "fixture.png",
                "mime_type": "image/png",
                "size_bytes": 68,
                "status": "READY",
                "visibility": "PUBLIC",
            },
        )
        await connection.execute(
            insert(HonorCategory),
            {
                "id": values["category"],
                "tenant_id": values["tenant"],
                "name": "Existing category",
                "slug": f"existing-{values['category']}",
                "sort_order": 0,
                "is_active": True,
            },
        )
        await connection.execute(
            insert(PricingPlan),
            {
                "id": values["plan"],
                "tenant_id": values["tenant"],
                "title": "Existing plan",
                "slug": f"existing-{values['plan']}",
                "description": "Existing plan",
                "mode": "ONLINE",
                "amount": 0,
                "currency": "IRR",
                "features": [],
                "sort_order": 0,
                "is_featured": False,
                "status": "PUBLISHED",
            },
        )
        await connection.execute(
            insert(ExamOffering),
            {
                "id": values["exam"],
                "tenant_id": values["tenant"],
                "title": "Existing exam",
                "slug": f"existing-{values['exam']}",
                "description": "Existing exam",
                "mode": "ONLINE",
                "status": "REGISTRATION_OPEN",
            },
        )
    return values


def _case(
    name: str, context: dict[str, uuid.UUID]
) -> tuple[type[Base], type[BaseModel], BaseModel, BaseModel, str]:
    suffix = uuid.uuid4().hex
    cases: dict[str, tuple[type[Base], type[BaseModel], BaseModel, BaseModel, str]] = {
        "post": (
            Post,
            PostAdmin,
            PostWrite(
                kind="NEWS",
                title="Initial news",
                slug=f"news-{suffix}",
                body="body",
                status="DRAFT",
            ),
            PostWrite(
                kind="NEWS",
                title="Updated news",
                slug=f"news-{suffix}",
                body="updated",
                status="PUBLISHED",
            ),
            "post",
        ),
        "banner": (
            Banner,
            BannerAdmin,
            BannerWrite(title="Initial banner", image_id=context["media"], status="DRAFT"),
            BannerWrite(title="Updated banner", image_id=context["media"], status="PUBLISHED"),
            "banner",
        ),
        "honor_category": (
            HonorCategory,
            HonorCategoryAdmin,
            HonorCategoryWrite(name="Initial category", slug=f"category-{suffix}"),
            HonorCategoryWrite(name="Updated category", slug=f"category-{suffix}"),
            "honor_category",
        ),
        "honor": (
            Honor,
            HonorAdmin,
            HonorWrite(
                category_id=context["category"],
                student_name="Initial Student",
                title="Initial honor",
            ),
            HonorWrite(
                category_id=context["category"],
                student_name="Updated Student",
                title="Updated honor",
                status="PUBLISHED",
            ),
            "honor",
        ),
        "staff": (
            StaffMember,
            StaffAdmin,
            StaffWrite(
                first_name="Initial",
                last_name="Teacher",
                display_name="Initial Teacher",
                member_type="TEACHER",
                title="Teacher",
            ),
            StaffWrite(
                first_name="Updated",
                last_name="Teacher",
                display_name="Updated Teacher",
                member_type="TEACHER",
                title="Senior Teacher",
            ),
            "staff_member",
        ),
        "pricing_plan": (
            PricingPlan,
            PricingPlanAdmin,
            PricingPlanWrite(
                title="Initial plan",
                slug=f"plan-{suffix}",
                description="Initial",
                mode="ONLINE",
                amount=0,
                currency="IRR",
            ),
            PricingPlanWrite(
                title="Updated plan",
                slug=f"plan-{suffix}",
                description="Updated",
                mode="ONLINE",
                amount=1000,
                currency="IRR",
                status="PUBLISHED",
            ),
            "pricing_plan",
        ),
        "exam": (
            ExamOffering,
            ExamOfferingAdmin,
            ExamOfferingWrite(
                title="Initial exam", slug=f"exam-{suffix}", description="Initial", mode="ONLINE"
            ),
            ExamOfferingWrite(
                title="Updated exam",
                slug=f"exam-{suffix}",
                description="Updated",
                mode="ONLINE",
                status="REGISTRATION_OPEN",
                pricing_plan_ids=[context["plan"]],
            ),
            "exam_offering",
        ),
        "sample_exam": (
            SampleExam,
            SampleExamAdmin,
            SampleExamWrite(title="Initial sample", file_media_id=context["media"]),
            SampleExamWrite(
                title="Updated sample", file_media_id=context["media"], status="PUBLISHED"
            ),
            "sample_exam",
        ),
        "gallery": (
            GalleryAlbum,
            GalleryAlbumAdmin,
            GalleryAlbumWrite(title="Initial gallery", slug=f"gallery-{suffix}"),
            GalleryAlbumWrite(
                title="Updated gallery", slug=f"gallery-{suffix}", status="PUBLISHED"
            ),
            "gallery_album",
        ),
    }
    return cases[name]


@pytest.mark.parametrize(
    "family",
    [
        "post",
        "banner",
        "honor_category",
        "honor",
        "staff",
        "pricing_plan",
        "exam",
        "sample_exam",
        "gallery",
    ],
)
async def test_generic_update_eagerly_loads_server_updated_timestamp_for_serialization(
    family: str,
    database: Database,
    update_context: dict[str, uuid.UUID],
) -> None:
    model, response_schema, create_body, update_body, entity_type = _case(family, update_context)
    service = AdminContentService()
    async with database.tenant_session(update_context["tenant"]) as session:
        entity = await service.create(
            session,
            model,
            tenant_id=update_context["tenant"],
            body=create_body,
            actor_user_id=update_context["actor"],
            entity_type=entity_type,
        )
        original_updated_at = entity.updated_at  # type: ignore[attr-defined]
        await service.update(
            session,
            entity,
            body=update_body,
            tenant_id=update_context["tenant"],
            actor_user_id=update_context["actor"],
            entity_type=entity_type,
        )
        assert "updated_at" not in inspect(entity).expired_attributes
        response = response_schema.model_validate(entity, from_attributes=True)
        assert response.updated_at >= original_updated_at  # type: ignore[attr-defined]


async def test_registration_patch_eagerly_loads_timestamp_and_preserves_unchanged_fields(
    database: Database,
    settings: Settings,
    update_context: dict[str, uuid.UUID],
) -> None:
    service = RegistrationService(settings)
    async with database.tenant_session(update_context["tenant"]) as session:
        registration = Registration(
            tenant_id=update_context["tenant"],
            exam_offering_id=update_context["exam"],
            selected_pricing_plan_id=update_context["plan"],
            draft_token_hash="0" * 64,
            draft_token_expires_at=datetime.now(UTC),
            phone_number="+989123456789",
            first_name="Unchanged",
            extra_answers={},
            payable_amount=0,
            payable_currency="IRR",
            status="PHONE_VERIFICATION_REQUIRED",
            payment_status="PENDING",
        )
        session.add(registration)
        await session.flush()
        original_updated_at = registration.updated_at
        await service.patch(
            session,
            registration,
            RegistrationPatch(
                last_name="Updated",
                gender="MALE",
                national_code="1234567891",
                father_name="Father",
                birth_date=date(2010, 1, 1),
                home_phone="02112345678",
                postal_code="1234567890",
                address="Updated address",
                extra_answers={"grade": "nine"},
            ),
        )
        assert "updated_at" not in inspect(registration).expired_attributes
        response = RegistrationResponse.model_validate(registration, from_attributes=True)
        assert response.first_name == "Unchanged"
        assert response.last_name == "Updated"
        assert response.updated_at >= original_updated_at
