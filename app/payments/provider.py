from __future__ import annotations

import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class InitiationResult:
    authority: str
    redirect_url: str


@dataclass(frozen=True, slots=True)
class VerificationResult:
    successful: bool
    provider_transaction_id: str | None = None
    failure_code: str | None = None
    failure_message: str | None = None


class PaymentGateway(Protocol):
    name: str

    async def initiate(
        self, *, amount: int, currency: str, callback_url: str, description: str
    ) -> InitiationResult: ...

    async def verify(
        self, *, authority: str, amount: int, currency: str, callback_data: Mapping[str, str]
    ) -> VerificationResult: ...


class MockPaymentGateway:
    name = "mock"

    def __init__(self) -> None:
        self.authorities: set[str] = set()

    async def initiate(
        self, *, amount: int, currency: str, callback_url: str, description: str
    ) -> InitiationResult:
        del amount, currency, description
        authority = secrets.token_urlsafe(24)
        self.authorities.add(authority)
        return InitiationResult(
            authority=authority,
            redirect_url=f"{callback_url}&authority={authority}&result=success",
        )

    async def verify(
        self, *, authority: str, amount: int, currency: str, callback_data: Mapping[str, str]
    ) -> VerificationResult:
        del amount, currency
        if authority not in self.authorities:
            return VerificationResult(False, failure_code="UNKNOWN_AUTHORITY")
        if callback_data.get("authority") != authority:
            return VerificationResult(False, failure_code="AUTHORITY_MISMATCH")
        if callback_data.get("result") != "success":
            return VerificationResult(False, failure_code="MOCK_PAYMENT_FAILED")
        return VerificationResult(True, provider_transaction_id=f"mock-{authority}")
