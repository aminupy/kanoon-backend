from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TimestampMixin, UUIDPrimaryKeyMixin


class TenantRole(StrEnum):
    TENANT_ADMIN = "TENANT_ADMIN"
    CONTENT_EDITOR = "CONTENT_EDITOR"
    REGISTRATION_MANAGER = "REGISTRATION_MANAGER"
    FINANCE_VIEWER = "FINANCE_VIEWER"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class TenantMembership(Base):
    __tablename__ = "tenant_memberships"
    __table_args__ = (Index("ix_tenant_memberships_tenant_role", "tenant_id", "role"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RefreshToken(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (Index("ix_refresh_tokens_user_active", "user_id", "revoked_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tenants.id"))
    family_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("refresh_tokens.id"))


class AuthenticationAttempt(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "authentication_attempts"
    __table_args__ = (Index("ix_auth_attempt_scope_created", "scope_hash", "created_at"),)

    scope_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
