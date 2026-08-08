from __future__ import annotations

import uuid
from datetime import date, datetime

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


class Banner(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "banners"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "image_id"], ["media_assets.tenant_id", "media_assets.id"]
        ),
        CheckConstraint("status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')", name="valid_status"),
        CheckConstraint(
            "ends_at IS NULL OR starts_at IS NULL OR ends_at > starts_at", name="valid_window"
        ),
        Index("ix_banners_tenant_public", "tenant_id", "status", "sort_order"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    image_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    target_url: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Post(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "posts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "kind", "slug"),
        ForeignKeyConstraint(
            ["tenant_id", "cover_image_id"], ["media_assets.tenant_id", "media_assets.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "og_image_id"], ["media_assets.tenant_id", "media_assets.id"]
        ),
        CheckConstraint("kind IN ('NEWS', 'ANNOUNCEMENT', 'BLOG')", name="valid_kind"),
        CheckConstraint("status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')", name="valid_status"),
        Index("ix_posts_tenant_kind_public", "tenant_id", "kind", "status", "published_at"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    content_document: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=lambda: {"type": "doc", "content": []}
    )
    rendered_html: Mapped[str | None] = mapped_column(Text)
    cover_image_id: Mapped[uuid.UUID | None]
    og_image_id: Mapped[uuid.UUID | None]
    seo_title: Mapped[str | None] = mapped_column(String(300))
    seo_description: Mapped[str | None] = mapped_column(String(500))
    event_date: Mapped[date | None] = mapped_column(Date)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")
    locale: Mapped[str | None] = mapped_column(String(20))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class PostMediaReference(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "post_media_references"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "post_id", "media_id"),
        ForeignKeyConstraint(
            ["tenant_id", "post_id"],
            ["posts.tenant_id", "posts.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "media_id"], ["media_assets.tenant_id", "media_assets.id"]
        ),
        Index("ix_post_media_references_tenant_post", "tenant_id", "post_id"),
        Index("ix_post_media_references_tenant_media", "tenant_id", "media_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    post_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    media_id: Mapped[uuid.UUID] = mapped_column(nullable=False)


class HonorCategory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "honor_categories"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "slug"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)


class Honor(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "honors"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "category_id"], ["honor_categories.tenant_id", "honor_categories.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "image_id"], ["media_assets.tenant_id", "media_assets.id"]
        ),
        CheckConstraint("status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')", name="valid_status"),
        Index("ix_honors_tenant_public", "tenant_id", "status", "sort_order"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    student_name: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    year: Mapped[int | None]
    rank: Mapped[int | None]
    institution_name: Mapped[str | None] = mapped_column(String(300))
    field_of_study: Mapped[str | None] = mapped_column(String(200))
    image_id: Mapped[uuid.UUID | None]
    sort_order: Mapped[int] = mapped_column(nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")


class StaffMember(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "staff_members"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "image_id"], ["media_assets.tenant_id", "media_assets.id"]
        ),
        CheckConstraint(
            "member_type IN ('TEACHER', 'EMPLOYEE', 'MANAGER', 'OTHER')", name="valid_type"
        ),
        Index("ix_staff_members_tenant_active", "tenant_id", "is_active", "sort_order"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    member_type: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    biography: Mapped[str | None] = mapped_column(Text)
    image_id: Mapped[uuid.UUID | None]
    public_phone: Mapped[str | None] = mapped_column(String(32))
    public_email: Mapped[str | None] = mapped_column(String(320))
    sort_order: Mapped[int] = mapped_column(nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)


class ContactRequest(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "contact_requests"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        CheckConstraint("status IN ('NEW', 'CONTACTED', 'CLOSED', 'SPAM')", name="valid_status"),
        Index("ix_contact_requests_tenant_status_created", "tenant_id", "status", "created_at"),
        Index(
            "ix_contact_requests_tenant_ip_created", "tenant_id", "request_ip_hash", "created_at"
        ),
        Index(
            "ix_contact_requests_tenant_phone_created", "tenant_id", "phone_number", "created_at"
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    education_level: Mapped[str] = mapped_column(String(100), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(16), nullable=False)
    request_ip_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="NEW")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    handled_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    internal_notes: Mapped[str | None] = mapped_column(Text)


class SampleExam(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sample_exams"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "file_media_id"], ["media_assets.tenant_id", "media_assets.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "cover_media_id"], ["media_assets.tenant_id", "media_assets.id"]
        ),
        CheckConstraint("status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')", name="valid_status"),
        CheckConstraint("download_count >= 0", name="download_count_nonnegative"),
        Index("ix_sample_exams_tenant_public", "tenant_id", "status", "sort_order"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    education_level: Mapped[str | None] = mapped_column(String(100))
    exam_year: Mapped[int | None]
    file_media_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    cover_media_id: Mapped[uuid.UUID | None]
    sort_order: Mapped[int] = mapped_column(nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")
    download_count: Mapped[int] = mapped_column(nullable=False, default=0)


class GalleryAlbum(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "gallery_albums"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "slug"),
        ForeignKeyConstraint(
            ["tenant_id", "cover_image_id"], ["media_assets.tenant_id", "media_assets.id"]
        ),
        CheckConstraint("status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')", name="valid_status"),
        Index("ix_gallery_albums_tenant_public", "tenant_id", "status", "sort_order"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    cover_image_id: Mapped[uuid.UUID | None]
    sort_order: Mapped[int] = mapped_column(nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")


class GalleryItem(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "gallery_items"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "album_id"],
            ["gallery_albums.tenant_id", "gallery_albums.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "media_id"], ["media_assets.tenant_id", "media_assets.id"]
        ),
        Index("ix_gallery_items_tenant_album_order", "tenant_id", "album_id", "sort_order"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    album_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    media_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    title: Mapped[str | None] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sort_order: Mapped[int] = mapped_column(nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SchoolDirectoryEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "school_directory_entries"

    name: Mapped[str] = mapped_column(String(300), nullable=False)
    city: Mapped[str | None] = mapped_column(String(150))
    province: Mapped[str | None] = mapped_column(String(150))
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
