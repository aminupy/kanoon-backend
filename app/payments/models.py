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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PaymentTransaction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payment_transactions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "idempotency_key"),
        UniqueConstraint("provider", "provider_transaction_id"),
        ForeignKeyConstraint(
            ["tenant_id", "registration_id"],
            ["registrations.tenant_id", "registrations.id"],
        ),
        CheckConstraint("amount >= 0", name="amount_nonnegative"),
        CheckConstraint(
            "status IN ('INITIATED', 'PENDING', 'SUCCESSFUL', 'FAILED', 'CANCELLED', 'REFUNDED')",
            name="valid_status",
        ),
        Index("ix_payment_transactions_tenant_registration", "tenant_id", "registration_id"),
        Index("ix_payment_transactions_tenant_status_created", "tenant_id", "status", "created_at"),
        Index(
            "uq_payment_transactions_active_registration",
            "tenant_id",
            "registration_id",
            unique=True,
            postgresql_where=text("status IN ('INITIATED', 'PENDING')"),
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    registration_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    amount: Mapped[int] = mapped_column(nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="INITIATED")
    provider_authority: Mapped[str | None] = mapped_column(String(255))
    provider_transaction_id: Mapped[str | None] = mapped_column(String(255))
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    callback_nonce_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    callback_state: Mapped[str] = mapped_column(Text, nullable=False)
    callback_consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(100))
    failure_message: Mapped[str | None] = mapped_column(Text)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
