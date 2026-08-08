from __future__ import annotations

import csv
import io
import uuid
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.core.database import Database
from app.core.errors import ApplicationError
from app.registrations.admin_schemas import RegistrationAdminUpdate
from app.registrations.models import Registration, RegistrationContact


class RegistrationAdminService:
    async def list(
        self,
        session: AsyncSession,
        *,
        status: str | None,
        search: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Registration], int]:
        statement = select(Registration)
        count_statement = select(func.count()).select_from(Registration)
        if status:
            statement = statement.where(Registration.status == status)
            count_statement = count_statement.where(Registration.status == status)
        if search:
            pattern = f"%{search.strip()}%"
            condition = or_(
                Registration.phone_number.ilike(pattern),
                Registration.national_code.ilike(pattern),
                Registration.first_name.ilike(pattern),
                Registration.last_name.ilike(pattern),
            )
            statement = statement.where(condition)
            count_statement = count_statement.where(condition)
        rows = list(
            (
                await session.scalars(
                    statement.order_by(Registration.created_at.desc()).offset(offset).limit(limit)
                )
            ).all()
        )
        return rows, (await session.scalar(count_statement) or 0)

    async def get(
        self, session: AsyncSession, registration_id: uuid.UUID, *, lock: bool = False
    ) -> Registration:
        statement = select(Registration).where(Registration.id == registration_id)
        if lock:
            statement = statement.with_for_update()
        registration = await session.scalar(statement)
        if registration is None:
            raise ApplicationError(
                "REGISTRATION_NOT_FOUND", "Registration was not found.", status_code=404
            )
        return registration

    async def contacts(
        self, session: AsyncSession, registration_id: uuid.UUID
    ) -> Sequence[RegistrationContact]:
        return list(
            (
                await session.scalars(
                    select(RegistrationContact)
                    .where(RegistrationContact.registration_id == registration_id)
                    .order_by(RegistrationContact.position)
                )
            ).all()
        )

    async def update(
        self,
        session: AsyncSession,
        *,
        registration: Registration,
        body: RegistrationAdminUpdate,
        actor_user_id: uuid.UUID,
    ) -> Registration:
        changes = body.model_dump(exclude_unset=True)
        if "status" in changes:
            requested = changes["status"]
            if requested == "SUBMITTED" and registration.status != "CANCELLED":
                raise ApplicationError(
                    "ADMIN_STATUS_TRANSITION_INVALID",
                    "Only a cancelled registration may be restored to submitted.",
                )
            if requested == "CANCELLED" and registration.status == "COMPLETED":
                raise ApplicationError(
                    "ADMIN_STATUS_TRANSITION_INVALID",
                    "A completed paid registration cannot be cancelled directly.",
                )
            registration.status = requested
        if "internal_notes" in changes:
            registration.internal_notes = changes["internal_notes"]
        session.add(
            AuditEvent(
                tenant_id=registration.tenant_id,
                actor_user_id=actor_user_id,
                action="registration.admin_updated",
                entity_type="registration",
                entity_id=registration.id,
                metadata_={"changed_fields": sorted(changes)},
                created_at=datetime.now(UTC),
            )
        )
        await session.flush()
        return registration

    async def record_export(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, actor_user_id: uuid.UUID
    ) -> None:
        session.add(
            AuditEvent(
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                action="registration.exported",
                entity_type="registration",
                metadata_={},
                created_at=datetime.now(UTC),
            )
        )


def csv_safe(value: object) -> str:
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return f"'{text}"
    return text


async def stream_registration_csv(database: Database, tenant_id: uuid.UUID) -> AsyncIterator[bytes]:
    columns = (
        "id",
        "exam_offering_id",
        "phone_number",
        "first_name",
        "last_name",
        "national_code",
        "status",
        "payment_status",
        "submitted_at",
        "created_at",
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    yield buffer.getvalue().encode("utf-8-sig")
    buffer.seek(0)
    buffer.truncate(0)
    async with database.tenant_session(tenant_id) as session:
        result = await session.stream(
            select(
                Registration.id,
                Registration.exam_offering_id,
                Registration.phone_number,
                Registration.first_name,
                Registration.last_name,
                Registration.national_code,
                Registration.status,
                Registration.payment_status,
                Registration.submitted_at,
                Registration.created_at,
            ).order_by(Registration.created_at)
        )
        async for row in result:
            writer.writerow(csv_safe(value) for value in row)
            yield buffer.getvalue().encode()
            buffer.seek(0)
            buffer.truncate(0)
