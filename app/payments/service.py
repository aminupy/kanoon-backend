from __future__ import annotations

import hmac
import secrets
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import sign_state, token_digest
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.payments.models import PaymentTransaction
from app.payments.provider import PaymentGateway
from app.payments.schemas import PaymentInitiateResponse
from app.registrations.models import Registration


class PaymentService:
    def __init__(self, settings: Settings, gateway: PaymentGateway) -> None:
        self.settings = settings
        self.gateway = gateway

    async def initiate(
        self,
        session: AsyncSession,
        *,
        registration: Registration,
        idempotency_key: str,
    ) -> PaymentInitiateResponse:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
            {"scope": f"payment:init:{registration.tenant_id}:{registration.id}"},
        )
        existing = await session.scalar(
            select(PaymentTransaction).where(PaymentTransaction.idempotency_key == idempotency_key)
        )
        if existing is not None:
            if existing.registration_id != registration.id:
                raise ApplicationError(
                    "IDEMPOTENCY_KEY_CONFLICT",
                    "Idempotency key is already in use.",
                    status_code=409,
                )
            return PaymentInitiateResponse(
                transaction_id=existing.id,
                status=existing.status,
                redirect_url=self._redirect(existing),
                amount=existing.amount,
                currency=existing.currency,
            )
        active = await session.scalar(
            select(PaymentTransaction).where(
                PaymentTransaction.registration_id == registration.id,
                PaymentTransaction.status.in_(("INITIATED", "PENDING")),
            )
        )
        if active is not None:
            raise ApplicationError(
                "PAYMENT_ALREADY_PENDING",
                "A payment attempt is already pending for this registration.",
                status_code=409,
            )
        if registration.status not in {"SUBMITTED", "PAYMENT_PENDING"}:
            raise ApplicationError(
                "REGISTRATION_NOT_PAYABLE", "Registration is not ready for payment."
            )
        if registration.payable_amount is None or registration.payable_amount <= 0:
            raise ApplicationError("PAYMENT_NOT_REQUIRED", "No online payment is required.")
        if registration.payable_currency is None:
            raise ApplicationError("PAYMENT_CURRENCY_MISSING", "Payment currency is unavailable.")

        transaction_id = uuid.uuid4()
        nonce = secrets.token_urlsafe(24)
        state = sign_state(
            self.settings,
            "payment_callback",
            {
                "tenant_id": str(registration.tenant_id),
                "transaction_id": str(transaction_id),
                "nonce": nonce,
                "provider": self.gateway.name,
            },
            self.settings.callback_token_ttl_seconds,
        )
        callback_url = (
            f"{self.settings.public_base_url.rstrip('/')}/api/v1/public/payments/callback/"
            f"{self.gateway.name}?state={state}"
        )
        result = await self.gateway.initiate(
            amount=registration.payable_amount,
            currency=registration.payable_currency,
            callback_url=callback_url,
            description=f"Exam registration {registration.id}",
        )
        transaction = PaymentTransaction(
            id=transaction_id,
            tenant_id=registration.tenant_id,
            registration_id=registration.id,
            provider=self.gateway.name,
            amount=registration.payable_amount,
            currency=registration.payable_currency,
            status="PENDING",
            provider_authority=result.authority,
            idempotency_key=idempotency_key,
            callback_nonce_hash=token_digest(nonce),
            callback_state=state,
        )
        session.add(transaction)
        registration.status = "PAYMENT_PENDING"
        await session.flush()
        return PaymentInitiateResponse(
            transaction_id=transaction.id,
            status=transaction.status,
            redirect_url=result.redirect_url,
            amount=transaction.amount,
            currency=transaction.currency,
        )

    def _redirect(self, transaction: PaymentTransaction) -> str:
        callback_url = (
            f"{self.settings.public_base_url.rstrip('/')}/api/v1/public/payments/callback/"
            f"{transaction.provider}?state={transaction.callback_state}"
        )
        if transaction.provider == "mock" and transaction.provider_authority:
            return f"{callback_url}&authority={transaction.provider_authority}&result=success"
        return callback_url

    async def verify_callback(
        self,
        session: AsyncSession,
        *,
        transaction_id: uuid.UUID,
        expected_nonce: str,
        callback_data: Mapping[str, str],
    ) -> PaymentTransaction:
        transaction = await session.scalar(
            select(PaymentTransaction)
            .where(PaymentTransaction.id == transaction_id)
            .with_for_update()
        )
        if transaction is None or transaction.provider != self.gateway.name:
            raise ApplicationError(
                "PAYMENT_TRANSACTION_NOT_FOUND", "Payment was not found.", status_code=404
            )
        if not hmac.compare_digest(token_digest(expected_nonce), transaction.callback_nonce_hash):
            raise ApplicationError(
                "PAYMENT_CALLBACK_INVALID", "Payment callback is invalid.", status_code=401
            )
        if transaction.status == "SUCCESSFUL":
            return transaction
        if transaction.callback_consumed_at is not None:
            return transaction
        if transaction.provider_authority is None:
            raise ApplicationError(
                "PAYMENT_CALLBACK_INVALID", "Payment callback is invalid.", status_code=401
            )
        result = await self.gateway.verify(
            authority=transaction.provider_authority,
            amount=transaction.amount,
            currency=transaction.currency,
            callback_data=callback_data,
        )
        now = datetime.now(UTC)
        transaction.callback_consumed_at = now
        registration = await session.scalar(
            select(Registration)
            .where(Registration.id == transaction.registration_id)
            .with_for_update()
        )
        if registration is None:
            raise ApplicationError(
                "REGISTRATION_NOT_FOUND", "Registration was not found.", status_code=404
            )
        if result.successful:
            transaction.status = "SUCCESSFUL"
            transaction.provider_transaction_id = result.provider_transaction_id
            transaction.verified_at = now
            registration.payment_status = "SUCCESSFUL"
            registration.status = "COMPLETED"
        else:
            transaction.status = "FAILED"
            transaction.failure_code = result.failure_code
            transaction.failure_message = result.failure_message
            registration.payment_status = "FAILED"
            registration.status = "SUBMITTED"
        await session.flush()
        return transaction
