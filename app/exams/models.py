from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ExamOffering(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "exam_offerings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "slug"),
        CheckConstraint("mode IN ('ONLINE', 'ONSITE')", name="valid_mode"),
        CheckConstraint(
            "status IN ('DRAFT', 'REGISTRATION_OPEN', 'REGISTRATION_CLOSED', "
            "'COMPLETED', 'ARCHIVED')",
            name="valid_status",
        ),
        CheckConstraint("capacity IS NULL OR capacity > 0", name="capacity_positive"),
        CheckConstraint(
            "registration_ends_at IS NULL OR registration_starts_at IS NULL OR "
            "registration_ends_at > registration_starts_at",
            name="valid_registration_window",
        ),
        CheckConstraint(
            "exam_ends_at IS NULL OR exam_starts_at IS NULL OR exam_ends_at > exam_starts_at",
            name="valid_exam_window",
        ),
        Index("ix_exam_offerings_tenant_public", "tenant_id", "status", "registration_starts_at"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    registration_starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    registration_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exam_starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exam_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    venue_name: Mapped[str | None] = mapped_column(String(300))
    venue_address: Mapped[str | None] = mapped_column(Text)
    capacity: Mapped[int | None]
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")


class PricingPlan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "pricing_plans"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "slug"),
        CheckConstraint("mode IN ('ONLINE', 'ONSITE')", name="valid_mode"),
        CheckConstraint("amount >= 0", name="amount_nonnegative"),
        CheckConstraint("status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')", name="valid_status"),
        Index("ix_pricing_plans_tenant_public", "tenant_id", "status", "sort_order"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[int] = mapped_column(nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    features: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    sort_order: Mapped[int] = mapped_column(nullable=False, default=0)
    is_featured: Mapped[bool] = mapped_column(nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")


class ExamPricingPlan(Base):
    __tablename__ = "exam_pricing_plans"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "exam_offering_id"],
            ["exam_offerings.tenant_id", "exam_offerings.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "pricing_plan_id"],
            ["pricing_plans.tenant_id", "pricing_plans.id"],
            ondelete="CASCADE",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    exam_offering_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    pricing_plan_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
