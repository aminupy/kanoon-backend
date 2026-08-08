from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Database
from app.core.errors import ApplicationError
from app.tenancy.context import TenantContext, tenant_context_from_request
from app.tenancy.models import TenantFeature


def get_database(request: Request) -> Database:
    return request.app.state.database  # type: ignore[no-any-return]


async def tenant_session(
    tenant: TenantContext = Depends(tenant_context_from_request),
    database: Database = Depends(get_database),
) -> AsyncIterator[AsyncSession]:
    async with database.tenant_session(tenant.tenant_id) as session:
        yield session


FeatureDependency = Callable[..., Coroutine[Any, Any, None]]


def require_feature(feature_key: str) -> FeatureDependency:
    async def dependency(
        tenant: TenantContext = Depends(tenant_context_from_request),
        session: AsyncSession = Depends(tenant_session),
    ) -> None:
        statement = select(TenantFeature.enabled).where(
            TenantFeature.tenant_id == tenant.tenant_id,
            TenantFeature.feature_key == feature_key,
        )
        enabled = (await session.execute(statement)).scalar_one_or_none()
        if enabled is not True:
            raise ApplicationError(
                "FEATURE_DISABLED",
                "This feature is not available for the requested site.",
                status_code=404,
            )

    return dependency
