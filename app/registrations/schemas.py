from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.registrations.validation import (
    normalize_iranian_mobile,
    require_past_birth_date,
    validate_iranian_national_code,
    validate_postal_code,
)


class RegistrationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    exam_offering_id: uuid.UUID
    selected_pricing_plan_id: uuid.UUID | None = None
    phone_number: str

    @field_validator("phone_number")
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        return normalize_iranian_mobile(value)


class RegistrationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phone_number: str | None = None
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    gender: Literal["FEMALE", "MALE", "OTHER"] | None = None
    national_code: str | None = None
    father_name: str | None = Field(default=None, min_length=1, max_length=200)
    birth_date: date | None = None
    home_phone: str | None = Field(default=None, max_length=32)
    current_school_id: uuid.UUID | None = None
    previous_school_id: uuid.UUID | None = None
    postal_code: str | None = None
    address: str | None = Field(default=None, min_length=5, max_length=4000)
    profile_image_id: uuid.UUID | None = None
    extra_answers: dict[str, Any] | None = None

    @field_validator("phone_number")
    @classmethod
    def normalize_phone(cls, value: str | None) -> str | None:
        return normalize_iranian_mobile(value) if value is not None else None

    @field_validator("national_code")
    @classmethod
    def national_code_checksum(cls, value: str | None) -> str | None:
        return validate_iranian_national_code(value) if value is not None else None

    @field_validator("postal_code")
    @classmethod
    def postal_code_format(cls, value: str | None) -> str | None:
        return validate_postal_code(value) if value is not None else None

    @field_validator("birth_date")
    @classmethod
    def birth_date_past(cls, value: date | None) -> date | None:
        return require_past_birth_date(value) if value is not None else None


class RegistrationContactInput(BaseModel):
    position: Literal[1, 2]
    name: str = Field(min_length=2, max_length=200)
    phone_number: str
    relationship: str = Field(min_length=2, max_length=100)

    @field_validator("phone_number")
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        return normalize_iranian_mobile(value)


class RegistrationContactsPut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contacts: list[RegistrationContactInput] = Field(min_length=1, max_length=2)

    @field_validator("contacts")
    @classmethod
    def positions_unique(
        cls, value: list[RegistrationContactInput]
    ) -> list[RegistrationContactInput]:
        if len({contact.position for contact in value}) != len(value):
            raise ValueError("contact positions must be unique")
        return value


class RegistrationContactResponse(RegistrationContactInput):
    id: uuid.UUID


class RegistrationResponse(BaseModel):
    id: uuid.UUID
    exam_offering_id: uuid.UUID
    selected_pricing_plan_id: uuid.UUID | None
    phone_number: str
    first_name: str | None
    last_name: str | None
    gender: str | None
    national_code: str | None
    father_name: str | None
    birth_date: date | None
    home_phone: str | None
    current_school_id: uuid.UUID | None
    previous_school_id: uuid.UUID | None
    postal_code: str | None
    address: str | None
    profile_image_id: uuid.UUID | None
    extra_answers: dict[str, Any]
    status: str
    payment_status: Literal["PENDING", "SUCCESSFUL", "FAILED"]
    payable_amount: int | None
    payable_currency: str | None
    phone_verified_at: datetime | None
    submitted_at: datetime | None
    created_at: datetime
    updated_at: datetime
    contacts: list[RegistrationContactResponse] = Field(default_factory=list)


class DraftCreated(BaseModel):
    registration: RegistrationResponse
    draft_token: str = Field(description="Shown once; store securely and send with Draft auth.")


class DraftTokenRotated(BaseModel):
    draft_token: str = Field(
        description="Replacement token shown once; the previous token is revoked."
    )
    expires_at: datetime


class OTPSendResponse(BaseModel):
    expires_at: datetime
    resend_after_seconds: int


class OTPVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^\d{6}$")


class OTPVerifyResponse(BaseModel):
    verified: bool
    phone_verified_at: datetime
