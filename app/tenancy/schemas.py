from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.auth.models import TenantRole
from app.tenancy.context import normalize_hostname
from app.tenancy.features import validate_feature_key
from app.tenancy.models import TenantStatus


class TenantCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=100)
    primary_hostname: str
    default_locale: str = Field(default="fa-IR", max_length=20)
    timezone: str = Field(default="Asia/Tehran", max_length=64)
    default_currency: str = Field(default="IRR", min_length=3, max_length=8)
    first_admin_email: EmailStr | None = None
    first_admin_password: str | None = Field(default=None, min_length=12, max_length=256)

    @field_validator("primary_hostname")
    @classmethod
    def normalized_hostname(cls, value: str) -> str:
        return normalize_hostname(value)


class TenantSummary(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    status: TenantStatus
    default_locale: str
    timezone: str
    default_currency: str
    created_at: datetime


class TenantStatusUpdate(BaseModel):
    status: TenantStatus


class DomainCreate(BaseModel):
    hostname: str
    is_primary: bool = False

    @field_validator("hostname")
    @classmethod
    def normalized_hostname(cls, value: str) -> str:
        return normalize_hostname(value)


class DomainResponse(BaseModel):
    id: uuid.UUID
    hostname: str
    is_primary: bool
    is_active: bool
    created_at: datetime


class FeatureUpdate(BaseModel):
    enabled: bool
    configuration: dict[str, object] = Field(default_factory=dict)


class FeatureResponse(FeatureUpdate):
    feature_key: str

    @field_validator("feature_key")
    @classmethod
    def known_feature(cls, value: str) -> str:
        return validate_feature_key(value)


class MembershipCreate(BaseModel):
    email: EmailStr
    password: str | None = Field(default=None, min_length=12, max_length=256)
    role: TenantRole
