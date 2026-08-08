from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import Settings

_password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def opaque_token() -> str:
    return secrets.token_urlsafe(48)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class AccessClaims:
    user_id: uuid.UUID
    tenant_id: uuid.UUID | None
    is_platform_admin: bool
    expires_at: datetime


def create_access_token(
    settings: Settings,
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID | None,
    is_platform_admin: bool,
) -> tuple[str, datetime]:
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=settings.access_token_ttl_seconds)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id) if tenant_id else None,
        "platform_admin": is_platform_admin,
        "iat": now,
        "exp": expires_at,
        "type": "access",
        "jti": str(uuid.uuid4()),
    }
    encoded = jwt.encode(payload, settings.signing_key.get_secret_value(), algorithm="HS256")
    return encoded, expires_at


def decode_access_token(settings: Settings, token: str) -> AccessClaims:
    payload = jwt.decode(
        token,
        settings.signing_key.get_secret_value(),
        algorithms=["HS256"],
        options={"require": ["sub", "exp", "iat", "type"]},
    )
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("wrong token type")
    tenant = payload.get("tenant_id")
    return AccessClaims(
        user_id=uuid.UUID(payload["sub"]),
        tenant_id=uuid.UUID(tenant) if tenant else None,
        is_platform_admin=bool(payload.get("platform_admin", False)),
        expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
    )


def sign_state(settings: Settings, purpose: str, payload: dict[str, Any], ttl_seconds: int) -> str:
    now = datetime.now(UTC)
    body = {
        **payload,
        "purpose": purpose,
        "iat": now,
        "exp": now + timedelta(seconds=ttl_seconds),
    }
    return jwt.encode(body, settings.signing_key.get_secret_value(), algorithm="HS256")


def verify_state(settings: Settings, purpose: str, token: str) -> dict[str, Any]:
    body: dict[str, Any] = jwt.decode(
        token,
        settings.signing_key.get_secret_value(),
        algorithms=["HS256"],
        options={"require": ["purpose", "iat", "exp"]},
    )
    if not hmac.compare_digest(str(body.get("purpose", "")), purpose):
        raise jwt.InvalidTokenError("state token purpose mismatch")
    return body
