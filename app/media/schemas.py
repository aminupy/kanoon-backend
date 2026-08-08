from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class UploadInitiateRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=3, max_length=127)
    size_bytes: int = Field(gt=0)
    alt_text: str | None = Field(default=None, max_length=500)
    visibility: Literal["PUBLIC", "PRIVATE"] = "PUBLIC"

    @field_validator("filename")
    @classmethod
    def basename_only(cls, value: str) -> str:
        if "/" in value or "\\" in value or value in {".", ".."}:
            raise ValueError("filename must not contain a path")
        return value


class UploadInitiateResponse(BaseModel):
    media_id: uuid.UUID
    upload_url: str
    form_fields: dict[str, str]
    expires_in: int


class UploadCompleteRequest(BaseModel):
    sha256: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")
    width: int | None = Field(default=None, gt=0, le=50000)
    height: int | None = Field(default=None, gt=0, le=50000)


class MediaResponse(BaseModel):
    id: uuid.UUID
    original_filename: str
    mime_type: str
    size_bytes: int
    width: int | None
    height: int | None
    alt_text: str | None
    status: str
    visibility: Literal["PUBLIC", "PRIVATE"]
