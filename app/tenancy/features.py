from __future__ import annotations

import uuid
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApplicationError
from app.tenancy.models import TenantFeature

FEATURE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "announcements",
        "banners",
        "blog",
        "contact_requests",
        "exam_registration",
        "gallery",
        "honors",
        "news",
        "online_payments",
        "pricing",
        "sample_exams",
        "school_profile",
        "staff",
    }
)


def validate_feature_key(value: str) -> str:
    if value not in FEATURE_KEYS:
        raise ValueError(f"unsupported feature key: {value}")
    return value


async def ensure_feature_enabled(
    session: AsyncSession, *, tenant_id: uuid.UUID, feature_key: str
) -> None:
    enabled = await session.scalar(
        select(TenantFeature.enabled).where(
            TenantFeature.tenant_id == tenant_id,
            TenantFeature.feature_key == feature_key,
        )
    )
    if enabled is not True:
        raise ApplicationError(
            "FEATURE_DISABLED",
            "This feature is not available for the requested site.",
            status_code=404,
        )
