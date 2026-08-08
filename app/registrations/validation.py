from __future__ import annotations

import re
from datetime import date

from app.core.errors import ApplicationError

_MOBILE_RE = re.compile(r"^989\d{9}$")
_DIGITS_RE = re.compile(r"^\d+$")


def normalize_iranian_mobile(value: str) -> str:
    compact = re.sub(r"[\s()-]", "", value)
    if compact.startswith("0098"):
        compact = compact[2:]
    elif compact.startswith("0"):
        compact = "98" + compact[1:]
    elif compact.startswith("+"):
        compact = compact[1:]
    if not _MOBILE_RE.fullmatch(compact):
        raise ValueError("invalid Iranian mobile number")
    return f"+{compact}"


def validate_postal_code(value: str) -> str:
    if len(value) != 10 or not _DIGITS_RE.fullmatch(value):
        raise ValueError("postal code must contain exactly 10 digits")
    return value


def validate_iranian_national_code(value: str) -> str:
    if len(value) != 10 or not _DIGITS_RE.fullmatch(value) or len(set(value)) == 1:
        raise ValueError("invalid national code")
    check = int(value[-1])
    remainder = sum(int(value[index]) * (10 - index) for index in range(9)) % 11
    expected = remainder if remainder < 2 else 11 - remainder
    if check != expected:
        raise ValueError("invalid national code checksum")
    return value


def require_past_birth_date(value: date) -> date:
    if value >= date.today():
        raise ValueError("birth date must be in the past")
    return value


def registration_error(code: str, message: str, *, status_code: int = 409) -> ApplicationError:
    return ApplicationError(code, message, status_code=status_code)
