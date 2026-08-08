from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, UUIDPrimaryKeyMixin


class AuditEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        Index("ix_audit_events_tenant_created", "tenant_id", "created_at"),
        Index("ix_audit_events_tenant_entity", "tenant_id", "entity_type", "entity_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[uuid.UUID | None]
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
