from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.site_builds.models import SiteBuildRequest, TenantSiteBuildConfig, TenantSiteState
from app.site_builds.schemas import SiteBuildStatus


class SiteBuildService:
    async def state_for_update(
        self, session: AsyncSession, tenant_id: uuid.UUID
    ) -> TenantSiteState:
        await session.execute(
            insert(TenantSiteState)
            .values(tenant_id=tenant_id, content_revision=0)
            .on_conflict_do_nothing(index_elements=["tenant_id"])
        )
        state = await session.scalar(
            select(TenantSiteState).where(TenantSiteState.tenant_id == tenant_id).with_for_update()
        )
        if state is None:  # pragma: no cover - guarded by insert + tenant context
            raise RuntimeError("tenant site state could not be established")
        return state

    async def public_content_changed(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        reason: str,
        entity_type: str | None,
        entity_id: uuid.UUID | None,
        created_by: uuid.UUID | None,
    ) -> SiteBuildRequest:
        state = await self.state_for_update(session, tenant_id)
        state.content_revision += 1
        return await self._enqueue(
            session,
            tenant_id=tenant_id,
            target_revision=state.content_revision,
            reason=reason,
            entity_type=entity_type,
            entity_id=entity_id,
            created_by=created_by,
        )

    async def manual_rebuild(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        created_by: uuid.UUID,
    ) -> SiteBuildRequest:
        state = await self.state_for_update(session, tenant_id)
        return await self._enqueue(
            session,
            tenant_id=tenant_id,
            target_revision=state.content_revision,
            reason="manual_rebuild",
            entity_type=None,
            entity_id=None,
            created_by=created_by,
        )

    async def _enqueue(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        target_revision: int,
        reason: str,
        entity_type: str | None,
        entity_id: uuid.UUID | None,
        created_by: uuid.UUID | None,
    ) -> SiteBuildRequest:
        now = datetime.now(UTC)
        pending = await session.scalar(
            select(SiteBuildRequest).where(SiteBuildRequest.status == "PENDING").with_for_update()
        )
        if pending is not None:
            pending.target_revision = max(pending.target_revision, target_revision)
            pending.reason = reason
            pending.entity_type = entity_type
            pending.entity_id = entity_id
            pending.created_by = created_by
            pending.requested_at = now
            pending.next_attempt_at = now
            pending.last_error = None
            await session.flush()
            return pending
        request = SiteBuildRequest(
            tenant_id=tenant_id,
            reason=reason,
            entity_type=entity_type,
            entity_id=entity_id,
            target_revision=target_revision,
            status="PENDING",
            requested_at=now,
            next_attempt_at=now,
            created_by=created_by,
        )
        session.add(request)
        await session.flush()
        return request

    async def status(self, session: AsyncSession) -> SiteBuildStatus:
        state = await session.scalar(select(TenantSiteState))
        latest = await session.scalar(
            select(SiteBuildRequest).order_by(desc(SiteBuildRequest.requested_at)).limit(1)
        )
        config = await session.scalar(select(TenantSiteBuildConfig.enabled))
        current = state.content_revision if state else 0
        deployed = state.last_successful_build_revision if state else None
        if config is not True:
            display_state = "NOT_CONFIGURED"
        elif latest is not None and latest.status == "RUNNING":
            display_state = "BUILDING"
        elif latest is not None and latest.status == "PENDING":
            display_state = "PENDING"
        elif latest is not None and latest.status == "FAILED" and (deployed or -1) < current:
            display_state = "FAILED"
        elif deployed is not None and deployed >= current:
            display_state = "UP_TO_DATE"
        else:
            display_state = "PENDING"
        return SiteBuildStatus(
            current_content_revision=current,
            deployed_revision=deployed,
            state=display_state,
            latest_request_id=latest.id if latest else None,
            latest_status=latest.status if latest else None,
            latest_target_revision=latest.target_revision if latest else None,
            latest_failure=latest.last_error if latest and latest.status == "FAILED" else None,
            requested_at=latest.requested_at if latest else None,
            completed_at=latest.completed_at if latest else None,
        )
