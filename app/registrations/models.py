from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
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


class RegistrationFormDefinition(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "registration_form_definitions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "version"),
        CheckConstraint("version > 0", name="version_positive"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Registration(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "registrations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "exam_offering_id", "national_code"),
        ForeignKeyConstraint(
            ["tenant_id", "exam_offering_id"],
            ["exam_offerings.tenant_id", "exam_offerings.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "selected_pricing_plan_id"],
            ["pricing_plans.tenant_id", "pricing_plans.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "profile_image_id"], ["media_assets.tenant_id", "media_assets.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "form_definition_id"],
            ["registration_form_definitions.tenant_id", "registration_form_definitions.id"],
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'PHONE_VERIFICATION_REQUIRED', 'PHONE_VERIFIED', "
            "'READY_FOR_SUBMISSION', 'SUBMITTED', 'PAYMENT_PENDING', 'COMPLETED', "
            "'CANCELLED')",
            name="valid_status",
        ),
        CheckConstraint(
            "payment_status IN ('PENDING', 'SUCCESSFUL', 'FAILED')", name="valid_payment_status"
        ),
        CheckConstraint(
            "gender IS NULL OR gender IN ('FEMALE', 'MALE', 'OTHER')", name="valid_gender"
        ),
        CheckConstraint(
            "payable_amount IS NULL OR payable_amount >= 0", name="payable_amount_nonnegative"
        ),
        Index("ix_registrations_tenant_status_created", "tenant_id", "status", "created_at"),
        Index("ix_registrations_tenant_phone", "tenant_id", "phone_number"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    exam_offering_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    selected_pricing_plan_id: Mapped[uuid.UUID | None]
    form_definition_id: Mapped[uuid.UUID | None]
    form_definition_version: Mapped[int | None]
    draft_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    draft_token_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    phone_number: Mapped[str] = mapped_column(String(16), nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    gender: Mapped[str | None] = mapped_column(String(16))
    national_code: Mapped[str | None] = mapped_column(String(10))
    father_name: Mapped[str | None] = mapped_column(String(200))
    birth_date: Mapped[date | None] = mapped_column(Date)
    home_phone: Mapped[str | None] = mapped_column(String(32))
    current_school_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("school_directory_entries.id")
    )
    previous_school_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("school_directory_entries.id")
    )
    postal_code: Mapped[str | None] = mapped_column(String(10))
    address: Mapped[str | None] = mapped_column(Text)
    profile_image_id: Mapped[uuid.UUID | None]
    extra_answers: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    payable_amount: Mapped[int | None]
    payable_currency: Mapped[str | None] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    payment_status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    internal_notes: Mapped[str | None] = mapped_column(Text)


class RegistrationContact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "registration_contacts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "registration_id", "position"),
        ForeignKeyConstraint(
            ["tenant_id", "registration_id"],
            ["registrations.tenant_id", "registrations.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("position IN (1, 2)", name="valid_position"),
        Index("ix_registration_contacts_tenant_registration", "tenant_id", "registration_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    registration_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    position: Mapped[int] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(16), nullable=False)
    relationship: Mapped[str] = mapped_column(String(100), nullable=False)


class OTPChallenge(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "otp_challenges"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "registration_id"],
            ["registrations.tenant_id", "registrations.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        Index(
            "ix_otp_challenges_tenant_registration_created",
            "tenant_id",
            "registration_id",
            "created_at",
        ),
        Index("ix_otp_challenges_tenant_phone_created", "tenant_id", "phone_number", "created_at"),
        Index("ix_otp_challenges_ip_created", "request_ip_hash", "created_at"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    registration_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    phone_number: Mapped[str] = mapped_column(String(16), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    attempt_count: Mapped[int] = mapped_column(nullable=False, default=0)
    request_ip_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
