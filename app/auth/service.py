from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import AuthenticationAttempt, RefreshToken, TenantMembership, User
from app.auth.schemas import TokenPair
from app.auth.security import create_access_token, opaque_token, token_digest, verify_password
from app.core.config import Settings
from app.core.errors import ApplicationError


class AuthenticationService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _scope_hash(self, email: str, client_ip: str) -> str:
        value = f"{email.casefold()}|{client_ip}".encode()
        return hmac.new(
            self.settings.signing_key.get_secret_value().encode(), value, hashlib.sha256
        ).hexdigest()

    async def enforce_rate_limit(self, session: AsyncSession, *, email: str, client_ip: str) -> str:
        scope_hash = self._scope_hash(email, client_ip)
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
            {"scope": f"auth:{scope_hash}"},
        )
        since = datetime.now(UTC) - timedelta(seconds=self.settings.authentication_window_seconds)
        attempts = await session.scalar(
            select(func.count())
            .select_from(AuthenticationAttempt)
            .where(
                AuthenticationAttempt.scope_hash == scope_hash,
                AuthenticationAttempt.created_at >= since,
                AuthenticationAttempt.succeeded.is_(False),
            )
        )
        if (attempts or 0) >= self.settings.authentication_max_attempts:
            raise ApplicationError(
                "AUTHENTICATION_RATE_LIMITED",
                "Too many authentication attempts. Try again later.",
                status_code=429,
            )
        return scope_hash

    async def authenticate_user(
        self,
        session: AsyncSession,
        *,
        email: str,
        password: str,
        client_ip: str,
        platform_only: bool,
    ) -> User | None:
        scope_hash = await self.enforce_rate_limit(session, email=email, client_ip=client_ip)
        normalized_email = email.casefold()
        user = await session.scalar(select(User).where(User.email == normalized_email))
        valid = (
            user is not None
            and user.is_active
            and (not platform_only or user.is_platform_admin)
            and verify_password(user.password_hash, password)
        )
        session.add(
            AuthenticationAttempt(
                scope_hash=scope_hash,
                succeeded=valid,
                created_at=datetime.now(UTC),
            )
        )
        return user if valid else None

    async def ensure_tenant_access(
        self, session: AsyncSession, *, user: User, tenant_id: uuid.UUID
    ) -> TenantMembership | None:
        membership = await session.scalar(
            select(TenantMembership).where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.user_id == user.id,
            )
        )
        if membership is None and not user.is_platform_admin:
            raise ApplicationError(
                "INVALID_CREDENTIALS", "Invalid email or password.", status_code=401
            )
        return membership

    async def issue_pair(
        self,
        session: AsyncSession,
        *,
        user: User,
        tenant_id: uuid.UUID | None,
        family_id: uuid.UUID | None = None,
    ) -> TokenPair:
        access_token, _ = create_access_token(
            self.settings,
            user_id=user.id,
            tenant_id=tenant_id,
            is_platform_admin=user.is_platform_admin,
        )
        raw_refresh = opaque_token()
        now = datetime.now(UTC)
        session.add(
            RefreshToken(
                user_id=user.id,
                tenant_id=tenant_id,
                family_id=family_id or uuid.uuid4(),
                token_hash=token_digest(raw_refresh),
                expires_at=now + timedelta(seconds=self.settings.refresh_token_ttl_seconds),
                created_at=now,
            )
        )
        await session.flush()
        return TokenPair(
            access_token=access_token,
            refresh_token=raw_refresh,
            expires_in=self.settings.access_token_ttl_seconds,
        )

    async def rotate_refresh_token(
        self,
        session: AsyncSession,
        *,
        raw_token: str,
        expected_tenant_id: uuid.UUID | None,
    ) -> tuple[TokenPair | None, bool]:
        digest = token_digest(raw_token)
        stored = await session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == digest).with_for_update()
        )
        now = datetime.now(UTC)
        if stored is None or stored.expires_at <= now:
            raise ApplicationError(
                "INVALID_REFRESH_TOKEN", "Refresh token is invalid.", status_code=401
            )
        if stored.tenant_id != expected_tenant_id:
            raise ApplicationError(
                "INVALID_REFRESH_TOKEN", "Refresh token is invalid.", status_code=401
            )
        if stored.revoked_at is not None:
            await session.execute(
                update(RefreshToken)
                .where(
                    RefreshToken.family_id == stored.family_id, RefreshToken.revoked_at.is_(None)
                )
                .values(revoked_at=now)
            )
            return None, True
        user = await session.get(User, stored.user_id)
        if user is None or not user.is_active:
            raise ApplicationError(
                "INVALID_REFRESH_TOKEN", "Refresh token is invalid.", status_code=401
            )
        stored.revoked_at = now
        pair = await self.issue_pair(
            session, user=user, tenant_id=stored.tenant_id, family_id=stored.family_id
        )
        replacement = await session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_digest(pair.refresh_token))
        )
        stored.replaced_by_id = replacement.id if replacement else None
        return pair, False
