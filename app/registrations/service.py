from __future__ import annotations

import hmac
import uuid
from datetime import UTC, datetime, timedelta

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JSONSchemaValidationError
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import opaque_token, token_digest
from app.content.models import SchoolDirectoryEntry
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.exams.models import ExamOffering, ExamPricingPlan, PricingPlan
from app.media.models import MediaAsset
from app.registrations.models import (
    OTPChallenge,
    Registration,
    RegistrationContact,
    RegistrationFormDefinition,
)
from app.registrations.schemas import (
    RegistrationContactInput,
    RegistrationPatch,
)

MUTABLE_STATUSES = frozenset(
    {"DRAFT", "PHONE_VERIFICATION_REQUIRED", "PHONE_VERIFIED", "READY_FOR_SUBMISSION"}
)
SUBMITTED_STATUSES = frozenset({"SUBMITTED", "PAYMENT_PENDING", "COMPLETED"})


class RegistrationService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def create_draft(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        exam_offering_id: uuid.UUID,
        pricing_plan_id: uuid.UUID | None,
        phone_number: str,
    ) -> tuple[Registration, str]:
        now = datetime.now(UTC)
        exam = await session.scalar(
            select(ExamOffering).where(ExamOffering.id == exam_offering_id).with_for_update()
        )
        if exam is None or exam.tenant_id != tenant_id:
            raise ApplicationError(
                "EXAM_NOT_FOUND", "Exam offering was not found.", status_code=404
            )
        if exam.status != "REGISTRATION_OPEN":
            raise ApplicationError("EXAM_REGISTRATION_CLOSED", "Exam registration is not open.")
        if exam.registration_starts_at and now < exam.registration_starts_at:
            raise ApplicationError("EXAM_REGISTRATION_NOT_STARTED", "Registration has not started.")
        if exam.registration_ends_at and now >= exam.registration_ends_at:
            raise ApplicationError("EXAM_REGISTRATION_CLOSED", "Exam registration has closed.")

        plan: PricingPlan | None = None
        if pricing_plan_id is not None:
            association = await session.scalar(
                select(ExamPricingPlan).where(
                    ExamPricingPlan.exam_offering_id == exam.id,
                    ExamPricingPlan.pricing_plan_id == pricing_plan_id,
                )
            )
            plan = await session.get(PricingPlan, pricing_plan_id)
            if association is None or plan is None or plan.status != "PUBLISHED":
                raise ApplicationError(
                    "PRICING_PLAN_NOT_AVAILABLE", "Pricing plan is not available for this exam."
                )

        definition = await session.scalar(
            select(RegistrationFormDefinition)
            .where(RegistrationFormDefinition.is_active.is_(True))
            .order_by(RegistrationFormDefinition.version.desc())
            .limit(1)
        )
        raw_token = opaque_token()
        registration = Registration(
            tenant_id=tenant_id,
            exam_offering_id=exam.id,
            selected_pricing_plan_id=plan.id if plan else None,
            form_definition_id=definition.id if definition else None,
            form_definition_version=definition.version if definition else None,
            draft_token_hash=token_digest(raw_token),
            draft_token_expires_at=now + timedelta(seconds=self.settings.draft_token_ttl_seconds),
            phone_number=phone_number,
            extra_answers={},
            payable_amount=plan.amount if plan else 0,
            payable_currency=plan.currency if plan else None,
            status="PHONE_VERIFICATION_REQUIRED",
            payment_status="PENDING",
        )
        session.add(registration)
        await session.flush()
        return registration, raw_token

    async def authorized_draft(
        self,
        session: AsyncSession,
        *,
        registration_id: uuid.UUID,
        raw_token: str,
        lock: bool = False,
    ) -> Registration:
        statement = select(Registration).where(Registration.id == registration_id)
        if lock:
            statement = statement.with_for_update()
        registration = await session.scalar(statement)
        now = datetime.now(UTC)
        valid = (
            registration is not None
            and registration.draft_token_expires_at > now
            and hmac.compare_digest(registration.draft_token_hash, token_digest(raw_token))
        )
        if not valid or registration is None:
            raise ApplicationError(
                "DRAFT_ACCESS_DENIED", "Registration draft access is denied.", status_code=404
            )
        return registration

    async def patch(
        self, session: AsyncSession, registration: Registration, body: RegistrationPatch
    ) -> Registration:
        if registration.status not in MUTABLE_STATUSES:
            raise ApplicationError(
                "REGISTRATION_NOT_EDITABLE", "Registration can no longer be edited."
            )
        changes = body.model_dump(exclude_unset=True)
        invalid_references: list[str] = []
        for field in ("current_school_id", "previous_school_id"):
            school_id = changes.get(field)
            if school_id is not None:
                school = await session.get(SchoolDirectoryEntry, school_id)
                if school is None or not school.is_active:
                    invalid_references.append(field)
        profile_image_id = changes.get("profile_image_id")
        if profile_image_id is not None:
            profile_image = await session.scalar(
                select(MediaAsset).where(
                    MediaAsset.id == profile_image_id,
                    MediaAsset.tenant_id == registration.tenant_id,
                )
            )
            if (
                profile_image is None
                or profile_image.status != "READY"
                or profile_image.visibility != "PRIVATE"
            ):
                invalid_references.append("profile_image_id")
        if invalid_references:
            raise ApplicationError(
                "REGISTRATION_REFERENCE_INVALID",
                "A referenced registration resource is unavailable.",
                status_code=422,
                details={"fields": invalid_references},
            )
        old_phone = registration.phone_number
        for field, value in changes.items():
            setattr(registration, field, value)
        if "phone_number" in changes and registration.phone_number != old_phone:
            registration.phone_verified_at = None
            registration.status = "PHONE_VERIFICATION_REQUIRED"
            await session.execute(
                update(OTPChallenge)
                .where(
                    OTPChallenge.registration_id == registration.id,
                    OTPChallenge.consumed_at.is_(None),
                    OTPChallenge.invalidated_at.is_(None),
                )
                .values(invalidated_at=datetime.now(UTC))
            )
        await session.flush()
        # TimestampMixin.updated_at is expired by its SQL-side on-update expression. Load it
        # while async I/O is still explicit so the router can serialize the object safely.
        await session.refresh(registration)
        return registration

    async def rotate_token(self, registration: Registration) -> str:
        raw_token = opaque_token()
        registration.draft_token_hash = token_digest(raw_token)
        registration.draft_token_expires_at = datetime.now(UTC) + timedelta(
            seconds=self.settings.draft_token_ttl_seconds
        )
        return raw_token

    async def replace_contacts(
        self,
        session: AsyncSession,
        registration: Registration,
        contacts: list[RegistrationContactInput],
    ) -> list[RegistrationContact]:
        if registration.status not in MUTABLE_STATUSES:
            raise ApplicationError(
                "REGISTRATION_NOT_EDITABLE", "Registration can no longer be edited."
            )
        await session.execute(
            delete(RegistrationContact).where(
                RegistrationContact.registration_id == registration.id
            )
        )
        stored = [
            RegistrationContact(
                tenant_id=registration.tenant_id,
                registration_id=registration.id,
                **contact.model_dump(),
            )
            for contact in contacts
        ]
        session.add_all(stored)
        await session.flush()
        return stored

    async def contacts(
        self, session: AsyncSession, registration_id: uuid.UUID
    ) -> list[RegistrationContact]:
        return list(
            (
                await session.scalars(
                    select(RegistrationContact)
                    .where(RegistrationContact.registration_id == registration_id)
                    .order_by(RegistrationContact.position)
                )
            ).all()
        )

    async def submit(self, session: AsyncSession, registration: Registration) -> Registration:
        if registration.status in SUBMITTED_STATUSES:
            return registration
        if registration.status not in MUTABLE_STATUSES:
            raise ApplicationError(
                "REGISTRATION_STATE_INVALID", "Registration cannot be submitted."
            )
        if registration.phone_verified_at is None:
            raise ApplicationError(
                "REGISTRATION_PHONE_NOT_VERIFIED",
                "Phone number must be verified before submission.",
            )
        required_values = {
            "first_name": registration.first_name,
            "last_name": registration.last_name,
            "gender": registration.gender,
            "national_code": registration.national_code,
            "father_name": registration.father_name,
            "birth_date": registration.birth_date,
            "current_school_id": registration.current_school_id,
            "previous_school_id": registration.previous_school_id,
            "postal_code": registration.postal_code,
            "address": registration.address,
            "profile_image_id": registration.profile_image_id,
        }
        missing = [name for name, value in required_values.items() if value is None]
        if missing:
            raise ApplicationError(
                "REGISTRATION_INCOMPLETE",
                "Registration is missing required fields.",
                details={"fields": missing},
            )
        contacts = await self.contacts(session, registration.id)
        if len(contacts) != 2 or {contact.position for contact in contacts} != {1, 2}:
            raise ApplicationError(
                "REGISTRATION_REQUIRES_TWO_CONTACTS",
                "Exactly two related contacts are required before submission.",
            )
        profile_image = await session.get(MediaAsset, registration.profile_image_id)
        if profile_image is None or profile_image.status != "READY":
            raise ApplicationError(
                "REGISTRATION_PROFILE_IMAGE_NOT_READY",
                "Profile image upload must be completed before submission.",
            )
        if registration.form_definition_id:
            definition = await session.get(
                RegistrationFormDefinition, registration.form_definition_id
            )
            if definition is None or definition.version != registration.form_definition_version:
                raise ApplicationError(
                    "REGISTRATION_FORM_VERSION_INVALID", "Registration form version is unavailable."
                )
            try:
                Draft202012Validator(definition.schema).validate(registration.extra_answers)
            except JSONSchemaValidationError as exc:
                raise ApplicationError(
                    "REGISTRATION_EXTRA_ANSWERS_INVALID",
                    "Additional answers do not match the registration form.",
                    details={"path": list(exc.absolute_path)},
                ) from exc

        exam = await session.scalar(
            select(ExamOffering)
            .where(ExamOffering.id == registration.exam_offering_id)
            .with_for_update()
        )
        if exam is None:
            raise ApplicationError(
                "EXAM_NOT_FOUND", "Exam offering was not found.", status_code=404
            )
        now = datetime.now(UTC)
        if exam.registration_ends_at and now >= exam.registration_ends_at:
            raise ApplicationError("EXAM_REGISTRATION_CLOSED", "Exam registration has closed.")
        if exam.capacity is not None:
            submitted_count = await session.scalar(
                select(func.count())
                .select_from(Registration)
                .where(
                    Registration.exam_offering_id == exam.id,
                    Registration.status.in_(SUBMITTED_STATUSES),
                )
            )
            if (submitted_count or 0) >= exam.capacity:
                raise ApplicationError("EXAM_CAPACITY_REACHED", "Exam capacity has been reached.")
        registration.status = "SUBMITTED"
        registration.submitted_at = now
        await session.flush()
        return registration
