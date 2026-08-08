from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field


class PaymentInitiateResponse(BaseModel):
    transaction_id: uuid.UUID
    status: str
    redirect_url: str
    amount: int = Field(ge=0)
    currency: str


class PaymentCallbackResponse(BaseModel):
    transaction_id: uuid.UUID
    status: Literal["SUCCESSFUL", "FAILED"]


class PaymentStatusResponse(BaseModel):
    registration_id: uuid.UUID
    payment_status: Literal["PENDING", "SUCCESSFUL", "FAILED"]
    latest_transaction_status: str | None
