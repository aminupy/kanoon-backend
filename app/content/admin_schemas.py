from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, HttpUrl, model_validator

from app.content.schemas import BannerWrite, PostWrite


class RecordMetadata(BaseModel):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class PostAdmin(PostWrite, RecordMetadata):
    pass


class BannerAdmin(BannerWrite, RecordMetadata):
    target_url: HttpUrl | None


class HonorCategoryWrite(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=150)
    description: str | None = Field(default=None, max_length=4000)
    sort_order: int = Field(default=0, ge=-100_000, le=100_000)
    is_active: bool = True


class HonorCategoryAdmin(HonorCategoryWrite, RecordMetadata):
    pass


class HonorWrite(BaseModel):
    category_id: uuid.UUID
    student_name: str = Field(min_length=2, max_length=200)
    title: str = Field(min_length=2, max_length=300)
    description: str | None = Field(default=None, max_length=10_000)
    year: int | None = Field(default=None, ge=1300, le=2500)
    rank: int | None = Field(default=None, ge=1)
    institution_name: str | None = Field(default=None, max_length=300)
    field_of_study: str | None = Field(default=None, max_length=200)
    image_id: uuid.UUID | None = None
    sort_order: int = Field(default=0, ge=-100_000, le=100_000)
    status: Literal["DRAFT", "PUBLISHED", "ARCHIVED"] = "DRAFT"


class HonorAdmin(HonorWrite, RecordMetadata):
    pass


class StaffWrite(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=2, max_length=200)
    member_type: Literal["TEACHER", "EMPLOYEE", "MANAGER", "OTHER"]
    title: str = Field(min_length=2, max_length=200)
    biography: str | None = Field(default=None, max_length=20_000)
    image_id: uuid.UUID | None = None
    public_phone: str | None = Field(default=None, max_length=32)
    public_email: EmailStr | None = None
    sort_order: int = Field(default=0, ge=-100_000, le=100_000)
    is_active: bool = True


class StaffAdmin(StaffWrite, RecordMetadata):
    pass


class PricingPlanWrite(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=200)
    description: str = Field(min_length=1, max_length=10_000)
    mode: Literal["ONLINE", "ONSITE"]
    amount: int = Field(ge=0)
    currency: str = Field(min_length=3, max_length=8)
    features: list[str] = Field(default_factory=list, max_length=30)
    sort_order: int = Field(default=0, ge=-100_000, le=100_000)
    is_featured: bool = False
    status: Literal["DRAFT", "PUBLISHED", "ARCHIVED"] = "DRAFT"


class PricingPlanAdmin(PricingPlanWrite, RecordMetadata):
    pass


class ExamOfferingWrite(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=200)
    description: str = Field(min_length=1, max_length=50_000)
    mode: Literal["ONLINE", "ONSITE"]
    registration_starts_at: datetime | None = None
    registration_ends_at: datetime | None = None
    exam_starts_at: datetime | None = None
    exam_ends_at: datetime | None = None
    venue_name: str | None = Field(default=None, max_length=300)
    venue_address: str | None = Field(default=None, max_length=4000)
    capacity: int | None = Field(default=None, gt=0)
    status: Literal[
        "DRAFT", "REGISTRATION_OPEN", "REGISTRATION_CLOSED", "COMPLETED", "ARCHIVED"
    ] = "DRAFT"
    pricing_plan_ids: list[uuid.UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def timestamp_ordering(self) -> ExamOfferingWrite:
        if (
            self.registration_starts_at
            and self.registration_ends_at
            and self.registration_ends_at <= self.registration_starts_at
        ):
            raise ValueError("registration end must be after registration start")
        if self.exam_starts_at and self.exam_ends_at and self.exam_ends_at <= self.exam_starts_at:
            raise ValueError("exam end must be after exam start")
        return self


class ExamOfferingAdmin(ExamOfferingWrite, RecordMetadata):
    pass


class SampleExamWrite(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    description: str | None = Field(default=None, max_length=10_000)
    education_level: str | None = Field(default=None, max_length=100)
    exam_year: int | None = Field(default=None, ge=1300, le=2500)
    file_media_id: uuid.UUID
    cover_media_id: uuid.UUID | None = None
    sort_order: int = Field(default=0, ge=-100_000, le=100_000)
    status: Literal["DRAFT", "PUBLISHED", "ARCHIVED"] = "DRAFT"


class SampleExamAdmin(SampleExamWrite, RecordMetadata):
    download_count: int


class GalleryAlbumWrite(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    cover_image_id: uuid.UUID | None = None
    sort_order: int = Field(default=0, ge=-100_000, le=100_000)
    status: Literal["DRAFT", "PUBLISHED", "ARCHIVED"] = "DRAFT"


class GalleryAlbumAdmin(GalleryAlbumWrite, RecordMetadata):
    pass


class GalleryItemWrite(BaseModel):
    media_id: uuid.UUID
    title: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=10_000)
    captured_at: datetime | None = None
    sort_order: int = Field(default=0, ge=-100_000, le=100_000)


class GalleryItemAdmin(GalleryItemWrite):
    id: uuid.UUID
    album_id: uuid.UUID
    created_at: datetime


class ProfileWrite(BaseModel):
    display_name: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=50_000)


class AddressWrite(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    address: str = Field(min_length=3, max_length=4000)
    latitude: str | None = Field(default=None, max_length=32)
    longitude: str | None = Field(default=None, max_length=32)
    sort_order: int = 0


class PhoneWrite(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    phone_number: str = Field(min_length=3, max_length=32)
    sort_order: int = 0


class SocialLinkWrite(BaseModel):
    platform: str = Field(min_length=1, max_length=64)
    url: HttpUrl
    sort_order: int = 0


class ProfileContactsWrite(BaseModel):
    profile: ProfileWrite
    addresses: list[AddressWrite] = Field(default_factory=list, max_length=20)
    phones: list[PhoneWrite] = Field(default_factory=list, max_length=20)
    social_links: list[SocialLinkWrite] = Field(default_factory=list, max_length=30)


class ContactRequestAdmin(BaseModel):
    id: uuid.UUID
    name: str
    education_level: str
    phone_number: str
    status: str
    created_at: datetime
    handled_at: datetime | None
    handled_by: uuid.UUID | None
    internal_notes: str | None


class ContactRequestAdminUpdate(BaseModel):
    status: Literal["NEW", "CONTACTED", "CLOSED", "SPAM"]
    internal_notes: str | None = Field(default=None, max_length=10_000)
