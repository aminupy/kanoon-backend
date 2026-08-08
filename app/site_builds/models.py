from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TimestampMixin, UUIDPrimaryKeyMixin


class TenantSiteState(Base):
    __tablename__ = "tenant_site_states"
    __table_args__ = (
        CheckConstraint("content_revision >= 0", name="content_revision_nonnegative"),
        CheckConstraint(
            "last_successful_build_revision IS NULL OR last_successful_build_revision >= 0",
            name="deployed_revision_nonnegative",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    content_revision: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_successful_build_revision: Mapped[int | None] = mapped_column(BigInteger)
    last_build_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TenantSiteBuildConfig(TimestampMixin, Base):
    __tablename__ = "tenant_site_build_configs"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    canonical_domain: Mapped[str] = mapped_column(String(253), nullable=False)
    build_target_key: Mapped[str] = mapped_column(String(200), nullable=False)
    deployment_target_key: Mapped[str] = mapped_column(String(200), nullable=False)


class SiteBuildRequest(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "site_build_requests"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'SUCCESSFUL', 'FAILED', 'SUPERSEDED')",
            name="valid_status",
        ),
        CheckConstraint("target_revision >= 0", name="target_revision_nonnegative"),
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        Index(
            "uq_site_build_requests_one_pending_per_tenant",
            "tenant_id",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
        ),
        Index(
            "uq_site_build_requests_one_running_per_tenant",
            "tenant_id",
            unique=True,
            postgresql_where=text("status = 'RUNNING'"),
        ),
        Index(
            "ix_site_build_requests_tenant_status_requested",
            "tenant_id",
            "status",
            "requested_at",
        ),
        Index("ix_site_build_requests_poll", "status", "next_attempt_at", "requested_at"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    reason: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(100))
    entity_id: Mapped[uuid.UUID | None]
    target_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_revision: Mapped[int | None] = mapped_column(BigInteger)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
