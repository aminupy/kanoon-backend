from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, TypeVar

from pydantic import AnyUrl, BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.content.admin_schemas import ContactRequestAdminUpdate, ProfileContactsWrite
from app.content.models import ContactRequest, GalleryItem, Post
from app.core.errors import ApplicationError
from app.core.models import Base
from app.exams.models import ExamOffering, ExamPricingPlan, PricingPlan
from app.tenancy.models import (
    TenantAddress,
    TenantPhone,
    TenantProfile,
    TenantSocialLink,
)

ModelT = TypeVar("ModelT", bound=Base)


def schema_values(body: BaseModel) -> dict[str, Any]:
    values = body.model_dump()
    values.pop("pricing_plan_ids", None)
    return {
        key: str(value) if isinstance(value, AnyUrl) else value for key, value in values.items()
    }


class AdminContentService:
    async def list(
        self,
        session: AsyncSession,
        model: type[ModelT],
        *,
        offset: int,
        limit: int,
        filters: dict[str, Any] | None = None,
    ) -> tuple[list[ModelT], int]:
        statement = select(model)
        count_statement = select(func.count()).select_from(model)
        for field, value in (filters or {}).items():
            condition = getattr(model, field) == value
            statement = statement.where(condition)
            count_statement = count_statement.where(condition)
        total = await session.scalar(count_statement) or 0
        rows = list((await session.scalars(statement.offset(offset).limit(limit))).all())
        return rows, total

    async def get(
        self,
        session: AsyncSession,
        model: type[ModelT],
        entity_id: uuid.UUID,
        *,
        lock: bool = False,
    ) -> ModelT:
        statement = select(model).where(model.id == entity_id)  # type: ignore[attr-defined]
        if lock:
            statement = statement.with_for_update()
        entity = await session.scalar(statement)
        if entity is None:
            raise ApplicationError(
                "ADMIN_RESOURCE_NOT_FOUND", "Resource was not found.", status_code=404
            )
        return entity

    async def create(
        self,
        session: AsyncSession,
        model: type[ModelT],
        *,
        tenant_id: uuid.UUID,
        body: BaseModel,
        actor_user_id: uuid.UUID,
        entity_type: str,
        extra: dict[str, Any] | None = None,
    ) -> ModelT:
        values = schema_values(body)
        values.update(extra or {})
        entity = model(tenant_id=tenant_id, **values)
        session.add(entity)
        await session.flush()
        await self.audit(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action=f"{entity_type}.created",
            entity_type=entity_type,
            entity_id=entity.id,  # type: ignore[attr-defined]
        )
        return entity

    async def update(
        self,
        session: AsyncSession,
        entity: ModelT,
        *,
        body: BaseModel,
        tenant_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        entity_type: str,
    ) -> ModelT:
        if (
            getattr(entity, "status", None) == "ARCHIVED"
            or getattr(entity, "archived_at", None) is not None
        ):
            raise ApplicationError(
                "ADMIN_RESOURCE_ARCHIVED",
                "An archived resource cannot be updated.",
                status_code=409,
            )
        for key, value in schema_values(body).items():
            setattr(entity, key, value)
        if (
            isinstance(entity, Post)
            and entity.status == "PUBLISHED"
            and entity.published_at is None
        ):
            entity.published_at = datetime.now(UTC)
        await session.flush()
        await self.audit(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action=f"{entity_type}.updated",
            entity_type=entity_type,
            entity_id=entity.id,  # type: ignore[attr-defined]
        )
        # ``updated_at`` is populated by the SQL expression in TimestampMixin. SQLAlchemy
        # expires that attribute after UPDATE, so response serialization would otherwise try
        # to issue synchronous lazy I/O from Pydantic and fail with MissingGreenlet.
        await session.refresh(entity)
        return entity

    async def archive_or_delete(
        self,
        session: AsyncSession,
        entity: ModelT,
        *,
        tenant_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        entity_type: str,
    ) -> None:
        if hasattr(entity, "status"):
            setattr(entity, "status", "ARCHIVED")  # noqa: B010 - generic mapped resource
        elif hasattr(entity, "is_active"):
            setattr(entity, "is_active", False)  # noqa: B010 - generic mapped resource
            if hasattr(entity, "archived_at"):
                setattr(  # noqa: B010 - generic mapped resource
                    entity, "archived_at", datetime.now(UTC)
                )
        else:
            await session.delete(entity)
        await self.audit(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action=f"{entity_type}.archived",
            entity_type=entity_type,
            entity_id=entity.id,  # type: ignore[attr-defined]
        )

    async def set_exam_plans(
        self,
        session: AsyncSession,
        exam: ExamOffering,
        plan_ids: Sequence[uuid.UUID],
    ) -> None:
        await session.execute(
            delete(ExamPricingPlan).where(ExamPricingPlan.exam_offering_id == exam.id)
        )
        for plan_id in set(plan_ids):
            plan = await session.get(PricingPlan, plan_id)
            if plan is None:
                raise ApplicationError(
                    "PRICING_PLAN_NOT_FOUND", "Pricing plan was not found.", status_code=422
                )
            session.add(
                ExamPricingPlan(
                    tenant_id=exam.tenant_id,
                    exam_offering_id=exam.id,
                    pricing_plan_id=plan.id,
                )
            )
        await session.flush()

    async def replace_profile(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        body: ProfileContactsWrite,
    ) -> TenantProfile:
        profile = await session.scalar(
            select(TenantProfile).where(TenantProfile.tenant_id == tenant_id).with_for_update()
        )
        if profile is None:
            profile = TenantProfile(tenant_id=tenant_id, **schema_values(body.profile))
            session.add(profile)
        else:
            for key, value in schema_values(body.profile).items():
                setattr(profile, key, value)
        await session.execute(delete(TenantAddress).where(TenantAddress.tenant_id == tenant_id))
        await session.execute(delete(TenantPhone).where(TenantPhone.tenant_id == tenant_id))
        await session.execute(
            delete(TenantSocialLink).where(TenantSocialLink.tenant_id == tenant_id)
        )
        session.add_all(
            TenantAddress(tenant_id=tenant_id, **schema_values(item)) for item in body.addresses
        )
        session.add_all(
            TenantPhone(tenant_id=tenant_id, **schema_values(item)) for item in body.phones
        )
        session.add_all(
            TenantSocialLink(tenant_id=tenant_id, **schema_values(item))
            for item in body.social_links
        )
        await session.flush()
        await self.audit(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action="tenant_profile.updated",
            entity_type="tenant_profile",
            entity_id=profile.id,
        )
        return profile

    async def reset_profile(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> None:
        profile = await session.scalar(
            select(TenantProfile).where(TenantProfile.tenant_id == tenant_id).with_for_update()
        )
        await session.execute(delete(TenantAddress).where(TenantAddress.tenant_id == tenant_id))
        await session.execute(delete(TenantPhone).where(TenantPhone.tenant_id == tenant_id))
        await session.execute(
            delete(TenantSocialLink).where(TenantSocialLink.tenant_id == tenant_id)
        )
        if profile is None:
            return
        profile_id = profile.id
        await session.delete(profile)
        await self.audit(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action="tenant_profile.reset",
            entity_type="tenant_profile",
            entity_id=profile_id,
        )
        await session.flush()

    async def add_gallery_item(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        album_id: uuid.UUID,
        body: BaseModel,
        actor_user_id: uuid.UUID,
    ) -> GalleryItem:
        item = GalleryItem(
            tenant_id=tenant_id,
            album_id=album_id,
            created_at=datetime.now(UTC),
            **schema_values(body),
        )
        session.add(item)
        await session.flush()
        await self.audit(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action="gallery_item.created",
            entity_type="gallery_item",
            entity_id=item.id,
        )
        return item

    async def handle_contact_request(
        self,
        session: AsyncSession,
        *,
        contact: ContactRequest,
        body: ContactRequestAdminUpdate,
        actor_user_id: uuid.UUID,
    ) -> ContactRequest:
        contact.status = body.status
        contact.internal_notes = body.internal_notes
        contact.handled_by = actor_user_id
        contact.handled_at = datetime.now(UTC)
        await self.audit(
            session,
            tenant_id=contact.tenant_id,
            actor_user_id=actor_user_id,
            action="contact_request.handled",
            entity_type="contact_request",
            entity_id=contact.id,
        )
        await session.flush()
        return contact

    async def audit(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        action: str,
        entity_type: str,
        entity_id: uuid.UUID,
    ) -> None:
        session.add(
            AuditEvent(
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                metadata_={},
                created_at=datetime.now(UTC),
            )
        )
