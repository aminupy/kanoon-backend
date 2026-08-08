from __future__ import annotations

from typing import Protocol


class OTPProvider(Protocol):
    name: str

    async def send_code(self, *, phone_number: str, code: str, tenant_slug: str) -> None: ...


class MockOTPProvider:
    name = "mock"

    def __init__(self) -> None:
        self.sent_codes: dict[str, str] = {}

    async def send_code(self, *, phone_number: str, code: str, tenant_slug: str) -> None:
        del tenant_slug
        # Test-only inspection surface. Codes are intentionally never logged.
        self.sent_codes[phone_number] = code
