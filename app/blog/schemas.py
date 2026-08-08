from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.blog.rich_text import validate_document


class BlogCreate(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=200)
    summary: str | None = Field(default=None, max_length=2000)
    content_document: dict[str, Any] = Field(default_factory=lambda: {"type": "doc", "content": []})
    cover_image_id: uuid.UUID | None = None
    seo_title: str | None = Field(default=None, max_length=300)
    seo_description: str | None = Field(default=None, max_length=500)
    og_image_id: uuid.UUID | None = None
    locale: str | None = Field(default=None, max_length=20)

    @field_validator("content_document")
    @classmethod
    def structured_document(cls, value: object) -> dict[str, Any]:
        return validate_document(value)


class BlogUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=300)
    slug: str | None = Field(default=None, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=200)
    summary: str | None = Field(default=None, max_length=2000)
    content_document: dict[str, Any] | None = None
    cover_image_id: uuid.UUID | None = None
    seo_title: str | None = Field(default=None, max_length=300)
    seo_description: str | None = Field(default=None, max_length=500)
    og_image_id: uuid.UUID | None = None
    locale: str | None = Field(default=None, max_length=20)

    @field_validator("content_document")
    @classmethod
    def structured_document(cls, value: object | None) -> dict[str, Any] | None:
        return None if value is None else validate_document(value)


class BlogAdmin(BaseModel):
    id: uuid.UUID
    title: str
    slug: str
    summary: str | None
    content_document: dict[str, Any]
    rendered_html: str | None
    cover_image_id: uuid.UUID | None
    seo_title: str | None
    seo_description: str | None
    og_image_id: uuid.UUID | None
    status: str
    published_at: datetime | None
    locale: str | None
    created_at: datetime
    updated_at: datetime


class PublicMediaReference(BaseModel):
    id: uuid.UUID
    url: str
    alt_text: str | None
    width: int | None
    height: int | None


class BlogPublicSummary(BaseModel):
    title: str
    slug: str
    summary: str | None
    cover_image: PublicMediaReference | None
    seo_title: str
    seo_description: str | None
    og_image: PublicMediaReference | None
    published_at: datetime
    updated_at: datetime
    locale: str | None


class BlogPublicDetail(BlogPublicSummary):
    content_document: dict[str, Any]
    rendered_html: str


class BlogSnapshot(BaseModel):
    schema_version: int = 1
    content_revision: int
    requested_revision: int | None = None
    posts: list[BlogPublicDetail]
