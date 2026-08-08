from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class RegistrationAdminSummary(BaseModel):
    id: uuid.UUID
    exam_offering_id: uuid.UUID
    phone_number: str
    first_name: str | None
    last_name: str | None
    national_code: str | None
    status: str
    payment_status: str
    submitted_at: datetime | None
    created_at: datetime


class ContactAdmin(BaseModel):
    position: int
    name: str
    phone_number: str
    relationship: str


class RegistrationAdminDetail(RegistrationAdminSummary):
    gender: str | None
    father_name: str | None
    birth_date: date | None
    home_phone: str | None
    current_school_id: uuid.UUID | None
    previous_school_id: uuid.UUID | None
    postal_code: str | None
    address: str | None
    profile_image_id: uuid.UUID | None
    payable_amount: int | None
    payable_currency: str | None
    phone_verified_at: datetime | None
    internal_notes: str | None
    contacts: list[ContactAdmin]


class RegistrationAdminUpdate(BaseModel):
    status: Literal["SUBMITTED", "CANCELLED"] | None = None
    internal_notes: str | None = Field(default=None, max_length=10_000)
