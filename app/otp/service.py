from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.otp.provider import OTPProvider
from app.registrations.models import OTPChallenge, Registration


class OTPService:
    def __init__(self, settings: Settings, provider: OTPProvider) -> None:
        self.settings = settings
        self.provider = provider

    def _hash_code(self, challenge_id: uuid.UUID, code: str) -> str:
        return hmac.new(
            self.settings.signing_key.get_secret_value().encode(),
            f"{challenge_id}:{code}".encode(),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _ip_hash(ip: str) -> str:
        return hashlib.sha256(ip.encode()).hexdigest()

    async def send(
        self,
        session: AsyncSession,
        *,
        registration: Registration,
        client_ip: str,
        tenant_slug: str,
    ) -> OTPChallenge:
        now = datetime.now(UTC)
        ip_hash = self._ip_hash(client_ip)
        # Cross-registration sends for the same abuse scopes are serialized in PostgreSQL.
        for scope in (
            f"otp:tenant:{registration.tenant_id}",
            f"otp:phone:{registration.tenant_id}:{registration.phone_number}",
            f"otp:ip:{ip_hash}",
        ):
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
                {"scope": scope},
            )
        hour_ago = now - timedelta(hours=1)
        minute_ago = now - timedelta(minutes=1)
        phone_count = await session.scalar(
            select(func.count())
            .select_from(OTPChallenge)
            .where(
                OTPChallenge.phone_number == registration.phone_number,
                OTPChallenge.created_at >= hour_ago,
            )
        )
        ip_count = await session.scalar(
            select(func.count())
            .select_from(OTPChallenge)
            .where(OTPChallenge.request_ip_hash == ip_hash, OTPChallenge.created_at >= hour_ago)
        )
        tenant_count = await session.scalar(
            select(func.count())
            .select_from(OTPChallenge)
            .where(OTPChallenge.created_at >= minute_ago)
        )
        if (
            (phone_count or 0) >= self.settings.otp_phone_hourly_limit
            or (ip_count or 0) >= self.settings.otp_ip_hourly_limit
            or (tenant_count or 0) >= self.settings.otp_tenant_minute_limit
        ):
            raise ApplicationError(
                "OTP_RATE_LIMITED",
                "Too many verification-code requests. Try again later.",
                status_code=429,
            )
        latest = await session.scalar(
            select(OTPChallenge)
            .where(
                OTPChallenge.tenant_id == registration.tenant_id,
                OTPChallenge.registration_id == registration.id,
            )
            .order_by(OTPChallenge.created_at.desc())
            .limit(1)
            .with_for_update()
        )
        if (
            latest
            and latest.created_at + timedelta(seconds=self.settings.otp_resend_cooldown_seconds)
            > now
        ):
            retry_after = int(
                (
                    latest.created_at
                    + timedelta(seconds=self.settings.otp_resend_cooldown_seconds)
                    - now
                ).total_seconds()
            )
            raise ApplicationError(
                "OTP_RESEND_COOLDOWN",
                "Wait before requesting another verification code.",
                status_code=429,
                details={"retry_after_seconds": max(retry_after, 1)},
            )
        active_count = await session.scalar(
            select(func.count())
            .select_from(OTPChallenge)
            .where(
                OTPChallenge.tenant_id == registration.tenant_id,
                OTPChallenge.registration_id == registration.id,
                OTPChallenge.consumed_at.is_(None),
                OTPChallenge.invalidated_at.is_(None),
                OTPChallenge.expires_at > now,
            )
        )
        if (active_count or 0) >= self.settings.otp_max_active_challenges:
            raise ApplicationError(
                "OTP_TOO_MANY_ACTIVE", "Too many active verification codes.", status_code=429
            )
        await session.execute(
            update(OTPChallenge)
            .where(
                OTPChallenge.tenant_id == registration.tenant_id,
                OTPChallenge.registration_id == registration.id,
                OTPChallenge.consumed_at.is_(None),
            )
            .values(invalidated_at=now)
        )
        challenge_id = uuid.uuid4()
        code = "".join(secrets.choice("0123456789") for _ in range(6))
        challenge = OTPChallenge(
            id=challenge_id,
            tenant_id=registration.tenant_id,
            registration_id=registration.id,
            phone_number=registration.phone_number,
            code_hash=self._hash_code(challenge_id, code),
            attempt_count=0,
            request_ip_hash=ip_hash,
            expires_at=now + timedelta(seconds=self.settings.otp_ttl_seconds),
            created_at=now,
        )
        session.add(challenge)
        await session.flush()
        await self.provider.send_code(
            phone_number=registration.phone_number, code=code, tenant_slug=tenant_slug
        )
        return challenge

    async def verify(
        self,
        session: AsyncSession,
        *,
        registration: Registration,
        code: str,
    ) -> datetime:
        now = datetime.now(UTC)
        challenge = await session.scalar(
            select(OTPChallenge)
            .where(
                OTPChallenge.tenant_id == registration.tenant_id,
                OTPChallenge.registration_id == registration.id,
                OTPChallenge.phone_number == registration.phone_number,
                OTPChallenge.consumed_at.is_(None),
                OTPChallenge.invalidated_at.is_(None),
            )
            .order_by(OTPChallenge.created_at.desc())
            .limit(1)
            .with_for_update()
        )
        if challenge is None or challenge.expires_at <= now:
            raise ApplicationError("OTP_EXPIRED", "Verification code is expired or unavailable.")
        if challenge.attempt_count >= self.settings.otp_max_attempts:
            challenge.invalidated_at = now
            raise ApplicationError("OTP_ATTEMPT_LIMIT", "Verification attempt limit reached.")
        challenge.attempt_count += 1
        supplied_hash = self._hash_code(challenge.id, code)
        if not hmac.compare_digest(challenge.code_hash, supplied_hash):
            if challenge.attempt_count >= self.settings.otp_max_attempts:
                challenge.invalidated_at = now
            raise ApplicationError("OTP_INVALID", "Verification code is invalid.")
        challenge.consumed_at = now
        registration.phone_verified_at = now
        registration.status = "PHONE_VERIFIED"
        return now
