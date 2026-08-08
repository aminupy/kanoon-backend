from __future__ import annotations

import hashlib
import hmac
import time

from app.core.errors import ApplicationError


def sign_message(secret: str, timestamp: int, method: str, path: str, body: bytes) -> str:
    prefix = f"{timestamp}.{method.upper()}.{path}.".encode()
    return hmac.new(secret.encode(), prefix + body, hashlib.sha256).hexdigest()


def verify_message(
    *,
    secret: str,
    timestamp_value: str | None,
    signature: str | None,
    method: str,
    path: str,
    body: bytes,
    max_age_seconds: int,
) -> None:
    try:
        timestamp = int(timestamp_value or "")
    except ValueError as exc:
        raise ApplicationError(
            "BUILD_SIGNATURE_INVALID", "Build authentication failed.", status_code=401
        ) from exc
    if abs(int(time.time()) - timestamp) > max_age_seconds:
        raise ApplicationError(
            "BUILD_SIGNATURE_EXPIRED", "Build authentication failed.", status_code=401
        )
    expected = sign_message(secret, timestamp, method, path, body)
    if signature is None or not hmac.compare_digest(signature, expected):
        raise ApplicationError(
            "BUILD_SIGNATURE_INVALID", "Build authentication failed.", status_code=401
        )
