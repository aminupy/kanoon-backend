from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.tenancy.context import TenantContext
from app.tenancy.models import Tenant, TenantDomain, TenantStatus


class TenantRepository:
    async def resolve_active_domain(
        self, session: AsyncSession, hostname: str
    ) -> TenantContext | None:
        statement = (
            select(Tenant, TenantDomain)
            .join(TenantDomain, TenantDomain.tenant_id == Tenant.id)
            .where(TenantDomain.hostname == hostname, TenantDomain.is_active.is_(True))
        )
        row = (await session.execute(statement)).one_or_none()
        if row is None:
            return None
        tenant, domain = row
        return TenantContext(
            tenant_id=tenant.id,
            slug=tenant.slug,
            hostname=domain.hostname,
            status=TenantStatus(tenant.status),
            default_locale=tenant.default_locale,
            timezone=tenant.timezone,
            default_currency=tenant.default_currency,
        )
