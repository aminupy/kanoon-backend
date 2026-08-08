from __future__ import annotations

import uuid

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TimestampMixin, UUIDPrimaryKeyMixin


class MediaAsset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "object_key"),
        CheckConstraint("size_bytes >= 0", name="size_nonnegative"),
        CheckConstraint("status IN ('PENDING', 'READY', 'REJECTED')", name="valid_status"),
        CheckConstraint("visibility IN ('PUBLIC', 'PRIVATE')", name="valid_visibility"),
        Index("ix_media_assets_tenant_created", "tenant_id", "created_at"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(127), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64))
    width: Mapped[int | None]
    height: Mapped[int | None]
    alt_text: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, default="PRIVATE")
