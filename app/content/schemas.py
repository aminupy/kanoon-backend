from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, field_validator

from app.registrations.validation import normalize_iranian_mobile


class SiteTenant(BaseModel):
    name: str
    slug: str
    locale: str
    timezone: str
    currency: str


class SiteProfile(BaseModel):
    display_name: str
    description: str | None


class PublicAddress(BaseModel):
    label: str
    address: str
    latitude: str | None
    longitude: str | None


class PublicPhone(BaseModel):
    label: str
    phone_number: str


class PublicSocialLink(BaseModel):
    platform: str
    url: str


class SiteBootstrap(BaseModel):
    tenant: SiteTenant
    profile: SiteProfile | None
    enabled_capabilities: list[str]
    addresses: list[PublicAddress]
    phones: list[PublicPhone]
    social_links: list[PublicSocialLink]


class BannerPublic(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    image_id: uuid.UUID
    target_url: str | None
    sort_order: int


class PostSummary(BaseModel):
    id: uuid.UUID
    title: str
    slug: str
    summary: str | None
    cover_image_id: uuid.UUID | None
    event_date: date | None
    published_at: datetime | None
    locale: str | None


class PostDetail(PostSummary):
    body: str


class HonorPublic(BaseModel):
    id: uuid.UUID
    category_id: uuid.UUID
    student_name: str
    title: str
    description: str | None
    year: int | None
    rank: int | None
    institution_name: str | None
    field_of_study: str | None
    image_id: uuid.UUID | None


class StaffPublic(BaseModel):
    id: uuid.UUID
    display_name: str
    member_type: str
    title: str
    biography: str | None
    image_id: uuid.UUID | None
    public_phone: str | None
    public_email: str | None


class PricingPlanPublic(BaseModel):
    id: uuid.UUID
    title: str
    slug: str
    description: str
    mode: str
    amount: int
    currency: str
    features: list[str]
    is_featured: bool


class ExamOfferingPublic(BaseModel):
    id: uuid.UUID
    title: str
    slug: str
    description: str
    mode: str
    registration_starts_at: datetime | None
    registration_ends_at: datetime | None
    exam_starts_at: datetime | None
    exam_ends_at: datetime | None
    venue_name: str | None
    venue_address: str | None
    capacity: int | None


class SampleExamPublic(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    education_level: str | None
    exam_year: int | None
    file_media_id: uuid.UUID
    cover_media_id: uuid.UUID | None


class GalleryItemPublic(BaseModel):
    id: uuid.UUID
    media_id: uuid.UUID
    title: str | None
    description: str | None
    captured_at: datetime | None
    sort_order: int


class GalleryAlbumPublic(BaseModel):
    id: uuid.UUID
    title: str
    slug: str
    description: str | None
    cover_image_id: uuid.UUID | None
    sort_order: int


class GalleryAlbumDetail(GalleryAlbumPublic):
    items: list[GalleryItemPublic]


class ContactRequestCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    education_level: str = Field(min_length=1, max_length=100)
    phone_number: str

    @field_validator("phone_number")
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        return normalize_iranian_mobile(value)


class ContactRequestAccepted(BaseModel):
    id: uuid.UUID
    status: str


class SchoolDirectoryPublic(BaseModel):
    id: uuid.UUID
    name: str
    city: str | None
    province: str | None


class PostWrite(BaseModel):
    kind: str = Field(pattern=r"^(NEWS|ANNOUNCEMENT|BLOG)$")
    title: str = Field(min_length=2, max_length=300)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=200)
    summary: str | None = Field(default=None, max_length=2000)
    body: str = Field(min_length=1, max_length=200_000)
    cover_image_id: uuid.UUID | None = None
    event_date: date | None = None
    published_at: datetime | None = None
    status: str = Field(pattern=r"^(DRAFT|PUBLISHED|ARCHIVED)$")
    locale: str | None = Field(default=None, max_length=20)


class BannerWrite(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    image_id: uuid.UUID
    target_url: HttpUrl | None = None
    sort_order: int = Field(default=0, ge=-100_000, le=100_000)
    status: str = Field(pattern=r"^(DRAFT|PUBLISHED|ARCHIVED)$")
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @field_validator("ends_at")
    @classmethod
    def window_valid(cls, value: datetime | None, info: Any) -> datetime | None:
        start = info.data.get("starts_at")
        if value is not None and start is not None and value <= start:
            raise ValueError("ends_at must be after starts_at")
        return value
