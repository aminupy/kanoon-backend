from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.auth.security import token_digest, verify_state
from app.content.models import SchoolDirectoryEntry
from app.core.config import Settings
from app.core.database import Database
from app.core.errors import ApplicationError
from app.exams.models import ExamOffering, ExamPricingPlan, PricingPlan
from app.media.models import MediaAsset
from app.otp.provider import MockOTPProvider
from app.otp.service import OTPService
from app.payments.models import PaymentTransaction
from app.payments.provider import MockPaymentGateway
from app.payments.service import PaymentService
from app.registrations.models import OTPChallenge, Registration
from app.registrations.schemas import (
    RegistrationContactInput,
    RegistrationPatch,
)
from app.registrations.service import RegistrationService
from app.tenancy.models import Tenant

pytestmark = pytest.mark.integration


@pytest.fixture
async def registration_domain(owner_engine: AsyncEngine) -> dict[str, uuid.UUID]:
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    exam_id, plan_id, media_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    current_school, previous_school = uuid.uuid4(), uuid.uuid4()
    async with owner_engine.begin() as connection:
        await connection.execute(
            insert(Tenant),
            [
                {
                    "id": tenant_a,
                    "name": "Registration A",
                    "slug": f"registration-a-{tenant_a}",
                    "status": "ACTIVE",
                    "default_locale": "fa-IR",
                    "timezone": "Asia/Tehran",
                    "default_currency": "IRR",
                },
                {
                    "id": tenant_b,
                    "name": "Registration B",
                    "slug": f"registration-b-{tenant_b}",
                    "status": "ACTIVE",
                    "default_locale": "fa-IR",
                    "timezone": "Asia/Tehran",
                    "default_currency": "IRR",
                },
            ],
        )
        await connection.execute(
            insert(SchoolDirectoryEntry),
            [
                {"id": current_school, "name": "Current", "is_active": True},
                {"id": previous_school, "name": "Previous", "is_active": True},
            ],
        )
        await connection.execute(
            insert(MediaAsset),
            {
                "id": media_id,
                "tenant_id": tenant_a,
                "object_key": f"tenants/{tenant_a}/profile.jpg",
                "original_filename": "profile.jpg",
                "mime_type": "image/jpeg",
                "size_bytes": 100,
                "status": "READY",
            },
        )
        await connection.execute(
            insert(ExamOffering),
            {
                "id": exam_id,
                "tenant_id": tenant_a,
                "title": "Entrance Exam",
                "slug": f"exam-{exam_id}",
                "description": "Exam",
                "mode": "ONLINE",
                "status": "REGISTRATION_OPEN",
                "capacity": 20,
            },
        )
        await connection.execute(
            insert(PricingPlan),
            {
                "id": plan_id,
                "tenant_id": tenant_a,
                "title": "Standard",
                "slug": f"plan-{plan_id}",
                "description": "Plan",
                "mode": "ONLINE",
                "amount": 1_500_000,
                "currency": "IRR",
                "features": [],
                "sort_order": 0,
                "is_featured": False,
                "status": "PUBLISHED",
            },
        )
        await connection.execute(
            insert(ExamPricingPlan),
            {
                "tenant_id": tenant_a,
                "exam_offering_id": exam_id,
                "pricing_plan_id": plan_id,
            },
        )
    return {
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "exam": exam_id,
        "plan": plan_id,
        "media": media_id,
        "current_school": current_school,
        "previous_school": previous_school,
    }


async def create_draft(
    database: Database, settings: Settings, domain: dict[str, uuid.UUID]
) -> tuple[uuid.UUID, str]:
    async with database.tenant_session(domain["tenant_a"]) as session:
        registration, raw_token = await RegistrationService(settings).create_draft(
            session,
            tenant_id=domain["tenant_a"],
            exam_offering_id=domain["exam"],
            pricing_plan_id=domain["plan"],
            phone_number="+989123456789",
        )
        return registration.id, raw_token


async def fill_registration(
    service: RegistrationService,
    session: AsyncSession,
    registration: Registration,
    domain: dict[str, uuid.UUID],
) -> None:
    await service.patch(
        session,
        registration,
        RegistrationPatch(
            first_name="Ali",
            last_name="Ahmadi",
            gender="MALE",
            national_code="1234567891",
            father_name="Reza",
            birth_date=date(2010, 1, 1),
            current_school_id=domain["current_school"],
            previous_school_id=domain["previous_school"],
            postal_code="1234567890",
            address="Tehran, Example Street",
            profile_image_id=domain["media"],
        ),
    )


async def test_draft_partial_update_phone_invalidation_and_cross_tenant_token(
    database: Database, settings: Settings, registration_domain: dict[str, uuid.UUID]
) -> None:
    registration_id, token = await create_draft(database, settings, registration_domain)
    async with database.tenant_session(registration_domain["tenant_a"]) as session:
        service = RegistrationService(settings)
        registration = await service.authorized_draft(
            session, registration_id=registration_id, raw_token=token, lock=True
        )
        registration.phone_verified_at = datetime.now(UTC)
        await service.patch(session, registration, RegistrationPatch(phone_number="+989123456788"))
        assert registration.phone_verified_at is None
        assert registration.status == "PHONE_VERIFICATION_REQUIRED"
    async with database.tenant_session(registration_domain["tenant_b"]) as session:
        with pytest.raises(ApplicationError) as denied:
            await RegistrationService(settings).authorized_draft(
                session, registration_id=registration_id, raw_token=token
            )
        assert denied.value.code == "DRAFT_ACCESS_DENIED"


async def test_submission_requires_verification_and_exactly_two_contacts(
    database: Database, settings: Settings, registration_domain: dict[str, uuid.UUID]
) -> None:
    registration_id, token = await create_draft(database, settings, registration_domain)
    async with database.tenant_session(registration_domain["tenant_a"]) as session:
        service = RegistrationService(settings)
        registration = await service.authorized_draft(
            session, registration_id=registration_id, raw_token=token, lock=True
        )
        await fill_registration(service, session, registration, registration_domain)
        with pytest.raises(ApplicationError) as not_verified:
            await service.submit(session, registration)
        assert not_verified.value.code == "REGISTRATION_PHONE_NOT_VERIFIED"
        registration.phone_verified_at = datetime.now(UTC)
        await service.replace_contacts(
            session,
            registration,
            [
                RegistrationContactInput(
                    position=1,
                    name="Parent One",
                    phone_number="+989111111111",
                    relationship="father",
                )
            ],
        )
        with pytest.raises(ApplicationError) as contacts_error:
            await service.submit(session, registration)
        assert contacts_error.value.code == "REGISTRATION_REQUIRES_TWO_CONTACTS"
        await service.replace_contacts(
            session,
            registration,
            [
                RegistrationContactInput(
                    position=1,
                    name="Parent One",
                    phone_number="+989111111111",
                    relationship="father",
                ),
                RegistrationContactInput(
                    position=2,
                    name="Parent Two",
                    phone_number="+989222222222",
                    relationship="mother",
                ),
            ],
        )
        submitted = await service.submit(session, registration)
        assert submitted.status == "SUBMITTED"
        assert submitted.payable_amount == 1_500_000
        assert submitted.payable_currency == "IRR"


async def test_duplicate_student_exam_is_rejected(
    database: Database, settings: Settings, registration_domain: dict[str, uuid.UUID]
) -> None:
    first_id, first_token = await create_draft(database, settings, registration_domain)
    second_id, second_token = await create_draft(database, settings, registration_domain)
    async with database.tenant_session(registration_domain["tenant_a"]) as session:
        service = RegistrationService(settings)
        first = await service.authorized_draft(
            session, registration_id=first_id, raw_token=first_token, lock=True
        )
        await service.patch(session, first, RegistrationPatch(national_code="1234567891"))
    with pytest.raises(IntegrityError):
        async with database.tenant_session(registration_domain["tenant_a"]) as session:
            service = RegistrationService(settings)
            second = await service.authorized_draft(
                session, registration_id=second_id, raw_token=second_token, lock=True
            )
            await service.patch(session, second, RegistrationPatch(national_code="1234567891"))


async def test_otp_attempt_limit_expiration_and_one_time_consumption(
    database: Database, settings: Settings, registration_domain: dict[str, uuid.UUID]
) -> None:
    registration_id, token = await create_draft(database, settings, registration_domain)
    provider = MockOTPProvider()
    otp_service = OTPService(settings, provider)
    async with database.tenant_session(registration_domain["tenant_a"]) as session:
        registration = await RegistrationService(settings).authorized_draft(
            session, registration_id=registration_id, raw_token=token, lock=True
        )
        challenge = await otp_service.send(
            session,
            registration=registration,
            client_ip="192.0.2.10",
            tenant_slug="tenant-a",
        )
        code = provider.sent_codes[registration.phone_number]
        assert challenge.code_hash != code
        with pytest.raises(ApplicationError) as cooldown:
            await otp_service.send(
                session,
                registration=registration,
                client_ip="192.0.2.10",
                tenant_slug="tenant-a",
            )
        assert cooldown.value.code == "OTP_RESEND_COOLDOWN"

    for expected_attempt in range(1, settings.otp_max_attempts + 1):
        deferred = None
        async with database.tenant_session(registration_domain["tenant_a"]) as session:
            registration = await RegistrationService(settings).authorized_draft(
                session, registration_id=registration_id, raw_token=token, lock=True
            )
            try:
                await otp_service.verify(session, registration=registration, code="000000")
            except ApplicationError as exc:
                deferred = exc
        assert deferred is not None and deferred.code == "OTP_INVALID"
        async with database.tenant_session(registration_domain["tenant_a"]) as session:
            stored = await session.get(OTPChallenge, challenge.id)
            assert stored is not None and stored.attempt_count == expected_attempt

    async with database.tenant_session(registration_domain["tenant_a"]) as session:
        registration = await RegistrationService(settings).authorized_draft(
            session, registration_id=registration_id, raw_token=token, lock=True
        )
        with pytest.raises(ApplicationError) as limited:
            await otp_service.verify(session, registration=registration, code=code)
        assert limited.value.code in {"OTP_EXPIRED", "OTP_ATTEMPT_LIMIT"}

    second_id, second_token = await create_draft(database, settings, registration_domain)
    async with database.tenant_session(registration_domain["tenant_a"]) as session:
        registration = await RegistrationService(settings).authorized_draft(
            session, registration_id=second_id, raw_token=second_token, lock=True
        )
        await otp_service.send(
            session, registration=registration, client_ip="192.0.2.11", tenant_slug="tenant-a"
        )
        fresh_code = provider.sent_codes[registration.phone_number]
    async with database.tenant_session(registration_domain["tenant_a"]) as session:
        registration = await RegistrationService(settings).authorized_draft(
            session, registration_id=second_id, raw_token=second_token, lock=True
        )
        verified = await otp_service.verify(session, registration=registration, code=fresh_code)
        assert verified is not None
    async with database.tenant_session(registration_domain["tenant_a"]) as session:
        registration = await RegistrationService(settings).authorized_draft(
            session, registration_id=second_id, raw_token=second_token, lock=True
        )
        with pytest.raises(ApplicationError):
            await otp_service.verify(session, registration=registration, code=fresh_code)

    expired_id, expired_token = await create_draft(database, settings, registration_domain)
    async with database.tenant_session(registration_domain["tenant_a"]) as session:
        registration = await RegistrationService(settings).authorized_draft(
            session, registration_id=expired_id, raw_token=expired_token, lock=True
        )
        expired_challenge = await otp_service.send(
            session, registration=registration, client_ip="192.0.2.12", tenant_slug="tenant-a"
        )
        expired_code = provider.sent_codes[registration.phone_number]
    async with database.tenant_session(registration_domain["tenant_a"]) as session:
        stored = await session.get(OTPChallenge, expired_challenge.id, with_for_update=True)
        assert stored is not None
        stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    async with database.tenant_session(registration_domain["tenant_a"]) as session:
        registration = await RegistrationService(settings).authorized_draft(
            session, registration_id=expired_id, raw_token=expired_token, lock=True
        )
        with pytest.raises(ApplicationError) as expired:
            await otp_service.verify(session, registration=registration, code=expired_code)
        assert expired.value.code == "OTP_EXPIRED"


async def test_payment_is_idempotent_verified_server_side_and_replay_safe(
    database: Database, settings: Settings, registration_domain: dict[str, uuid.UUID]
) -> None:
    now = datetime.now(UTC)
    raw_token = "draft-token-that-is-long-enough-for-testing-123456789"
    async with database.tenant_session(registration_domain["tenant_a"]) as session:
        registration = Registration(
            tenant_id=registration_domain["tenant_a"],
            exam_offering_id=registration_domain["exam"],
            selected_pricing_plan_id=registration_domain["plan"],
            draft_token_hash=token_digest(raw_token),
            draft_token_expires_at=now + timedelta(hours=1),
            phone_number="+989123456789",
            payable_amount=1_500_000,
            payable_currency="IRR",
            status="SUBMITTED",
            payment_status="PENDING",
            extra_answers={},
        )
        session.add(registration)
        await session.flush()
        registration_id = registration.id

    gateway = MockPaymentGateway()
    payment_service = PaymentService(settings, gateway)
    async with database.tenant_session(registration_domain["tenant_a"]) as session:
        loaded_registration = await session.scalar(
            select(Registration).where(Registration.id == registration_id).with_for_update()
        )
        assert loaded_registration is not None
        initiated = await payment_service.initiate(
            session, registration=loaded_registration, idempotency_key="payment-attempt-1"
        )
        repeated = await payment_service.initiate(
            session, registration=loaded_registration, idempotency_key="payment-attempt-1"
        )
        assert repeated.transaction_id == initiated.transaction_id

    async with database.tenant_session(registration_domain["tenant_a"]) as session:
        transaction = await session.get(PaymentTransaction, initiated.transaction_id)
        assert transaction is not None and transaction.status == "PENDING"
        claims = verify_state(settings, "payment_callback", transaction.callback_state)
        authority = transaction.provider_authority
    assert authority is not None
    callback = {"authority": authority, "result": "success"}
    async with database.tenant_session(registration_domain["tenant_a"]) as session:
        with pytest.raises(ApplicationError) as invalid_nonce:
            await payment_service.verify_callback(
                session,
                transaction_id=initiated.transaction_id,
                expected_nonce="wrong-nonce",
                callback_data=callback,
            )
        assert invalid_nonce.value.code == "PAYMENT_CALLBACK_INVALID"
    async with database.tenant_session(registration_domain["tenant_b"]) as session:
        with pytest.raises(ApplicationError) as wrong_tenant:
            await payment_service.verify_callback(
                session,
                transaction_id=initiated.transaction_id,
                expected_nonce=str(claims["nonce"]),
                callback_data=callback,
            )
        assert wrong_tenant.value.code == "PAYMENT_TRANSACTION_NOT_FOUND"
    async with database.tenant_session(registration_domain["tenant_a"]) as session:
        verified = await payment_service.verify_callback(
            session,
            transaction_id=initiated.transaction_id,
            expected_nonce=str(claims["nonce"]),
            callback_data=callback,
        )
        assert verified.status == "SUCCESSFUL"
    async with database.tenant_session(registration_domain["tenant_a"]) as session:
        replay = await payment_service.verify_callback(
            session,
            transaction_id=initiated.transaction_id,
            expected_nonce=str(claims["nonce"]),
            callback_data=callback,
        )
        completed_registration = await session.get(Registration, registration_id)
        assert replay.status == "SUCCESSFUL"
        assert completed_registration is not None
        assert completed_registration.payment_status == "SUCCESSFUL"
        assert completed_registration.status == "COMPLETED"

    failed_raw_token = "another-draft-token-long-enough-for-testing-123456"
    async with database.tenant_session(registration_domain["tenant_a"]) as session:
        failed_registration = Registration(
            tenant_id=registration_domain["tenant_a"],
            exam_offering_id=registration_domain["exam"],
            selected_pricing_plan_id=registration_domain["plan"],
            draft_token_hash=token_digest(failed_raw_token),
            draft_token_expires_at=now + timedelta(hours=1),
            phone_number="+989123456788",
            payable_amount=1_500_000,
            payable_currency="IRR",
            status="SUBMITTED",
            payment_status="PENDING",
            extra_answers={},
        )
        session.add(failed_registration)
        await session.flush()
        failed_registration_id = failed_registration.id
        failed_initiation = await payment_service.initiate(
            session,
            registration=failed_registration,
            idempotency_key="payment-attempt-failed",
        )
    async with database.tenant_session(registration_domain["tenant_a"]) as session:
        failed_transaction = await session.get(PaymentTransaction, failed_initiation.transaction_id)
        assert failed_transaction is not None
        failed_claims = verify_state(
            settings, "payment_callback", failed_transaction.callback_state
        )
        failed_authority = failed_transaction.provider_authority
    assert failed_authority is not None
    async with database.tenant_session(registration_domain["tenant_a"]) as session:
        failed = await payment_service.verify_callback(
            session,
            transaction_id=failed_initiation.transaction_id,
            expected_nonce=str(failed_claims["nonce"]),
            callback_data={"authority": failed_authority, "result": "failed"},
        )
        loaded_failed_registration = await session.get(Registration, failed_registration_id)
        assert failed.status == "FAILED"
        assert loaded_failed_registration is not None
        assert loaded_failed_registration.payment_status == "FAILED"
        assert loaded_failed_registration.status == "SUBMITTED"
