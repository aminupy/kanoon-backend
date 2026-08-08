from __future__ import annotations

import uuid

import jwt
from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import verify_state
from app.core.database import Database
from app.core.errors import ApplicationError
from app.payments.models import PaymentTransaction
from app.payments.provider import PaymentGateway
from app.payments.schemas import (
    PaymentCallbackResponse,
    PaymentInitiateResponse,
    PaymentStatusResponse,
)
from app.payments.service import PaymentService
from app.registrations.router import draft_token
from app.registrations.service import RegistrationService
from app.tenancy.dependencies import get_database, require_feature, tenant_session

registration_payment_router = APIRouter(
    prefix="/api/v1/public/registrations",
    tags=["public-payments"],
    dependencies=[Depends(require_feature("online_payments"))],
)
callback_router = APIRouter(prefix="/api/v1/public/payments", tags=["payment-callbacks"])


@registration_payment_router.post(
    "/{registration_id}/payment", response_model=PaymentInitiateResponse
)
async def initiate_payment(
    registration_id: uuid.UUID,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    token: str = Depends(draft_token),
    session: AsyncSession = Depends(tenant_session),
) -> PaymentInitiateResponse:
    registration_service = RegistrationService(request.app.state.settings)
    registration = await registration_service.authorized_draft(
        session, registration_id=registration_id, raw_token=token, lock=True
    )
    gateway: PaymentGateway = request.app.state.payment_gateway
    service = PaymentService(request.app.state.settings, gateway)
    return await service.initiate(
        session, registration=registration, idempotency_key=idempotency_key
    )


@registration_payment_router.get(
    "/{registration_id}/payment/status", response_model=PaymentStatusResponse
)
async def payment_status(
    registration_id: uuid.UUID,
    request: Request,
    token: str = Depends(draft_token),
    session: AsyncSession = Depends(tenant_session),
) -> PaymentStatusResponse:
    registration_service = RegistrationService(request.app.state.settings)
    registration = await registration_service.authorized_draft(
        session, registration_id=registration_id, raw_token=token
    )
    latest = await session.scalar(
        select(PaymentTransaction)
        .where(PaymentTransaction.registration_id == registration.id)
        .order_by(PaymentTransaction.created_at.desc())
        .limit(1)
    )
    return PaymentStatusResponse(
        registration_id=registration.id,
        payment_status=registration.payment_status,
        latest_transaction_status=latest.status if latest else None,
    )


@callback_router.get(
    "/callback/{provider_name}",
    response_model=PaymentCallbackResponse,
    summary="Gateway callback; tenant is established from signed state",
)
async def payment_callback(
    provider_name: str,
    request: Request,
    state: str,
    database: Database = Depends(get_database),
) -> PaymentCallbackResponse:
    gateway: PaymentGateway = request.app.state.payment_gateway
    if provider_name != gateway.name:
        raise ApplicationError(
            "PAYMENT_PROVIDER_NOT_FOUND", "Payment provider is unavailable.", status_code=404
        )
    try:
        claims = verify_state(request.app.state.settings, "payment_callback", state)
        tenant_id = uuid.UUID(str(claims["tenant_id"]))
        transaction_id = uuid.UUID(str(claims["transaction_id"]))
        nonce = str(claims["nonce"])
        if claims.get("provider") != provider_name:
            raise ValueError("provider mismatch")
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise ApplicationError(
            "PAYMENT_CALLBACK_INVALID", "Payment callback is invalid.", status_code=401
        ) from exc
    callback_data = {key: value for key, value in request.query_params.items() if key != "state"}
    async with database.tenant_session(tenant_id) as session:
        transaction = await PaymentService(request.app.state.settings, gateway).verify_callback(
            session,
            transaction_id=transaction_id,
            expected_nonce=nonce,
            callback_data=callback_data,
        )
    status_value = "SUCCESSFUL" if transaction.status == "SUCCESSFUL" else "FAILED"
    return PaymentCallbackResponse(transaction_id=transaction.id, status=status_value)
