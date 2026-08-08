from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TimestampMixin, UUIDPrimaryKeyMixin


class TenantStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    ARCHIVED = "ARCHIVED"


class Tenant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=TenantStatus.ACTIVE.value
    )
    default_locale: Mapped[str] = mapped_column(String(20), nullable=False, default="fa-IR")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Tehran")
    default_currency: Mapped[str] = mapped_column(String(8), nullable=False, default="IRR")


class TenantDomain(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "tenant_domains"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    hostname: Mapped[str] = mapped_column(String(253), unique=True, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TenantFeature(TimestampMixin, Base):
    __tablename__ = "tenant_features"
    __table_args__ = (Index("ix_tenant_features_tenant_enabled", "tenant_id", "enabled"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    feature_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class TenantProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tenant_profiles"
    __table_args__ = (UniqueConstraint("tenant_id"), UniqueConstraint("tenant_id", "id"))

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class TenantAddress(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tenant_addresses"
    __table_args__ = (UniqueConstraint("tenant_id", "id"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    latitude: Mapped[str | None] = mapped_column(String(32))
    longitude: Mapped[str | None] = mapped_column(String(32))
    sort_order: Mapped[int] = mapped_column(nullable=False, default=0)


class TenantPhone(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tenant_phones"
    __table_args__ = (UniqueConstraint("tenant_id", "id"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(32), nullable=False)
    sort_order: Mapped[int] = mapped_column(nullable=False, default=0)


class TenantSocialLink(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tenant_social_links"
    __table_args__ = (UniqueConstraint("tenant_id", "id"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    platform: Mapped[str] = mapped_column(String(64), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(nullable=False, default=0)
