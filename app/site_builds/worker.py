from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select

from app.core.config import Settings
from app.core.database import Database
from app.site_builds.executor import SiteBuildExecutor
from app.site_builds.models import SiteBuildRequest, TenantSiteBuildConfig
from app.tenancy.models import Tenant

logger = structlog.get_logger(__name__)


class SiteBuildWorker:
    def __init__(self, database: Database, settings: Settings, executor: SiteBuildExecutor) -> None:
        self.database = database
        self.settings = settings
        self.executor = executor

    async def run_once(self) -> int:
        async with self.database.global_session() as session:
            tenant_ids = list((await session.scalars(select(Tenant.id))).all())
        claimed = 0
        for tenant_id in tenant_ids:
            request = await self._claim(tenant_id)
            if request is None:
                continue
            claimed += 1
            await self._trigger(tenant_id, request)
        return claimed

    async def run_forever(self) -> None:
        while True:
            claimed = await self.run_once()
            if claimed == 0:
                await asyncio.sleep(self.settings.site_build_poll_seconds)

    async def _claim(self, tenant_id: uuid.UUID) -> SiteBuildRequest | None:
        now = datetime.now(UTC)
        async with self.database.tenant_session(tenant_id) as session:
            config = await session.scalar(
                select(TenantSiteBuildConfig).where(TenantSiteBuildConfig.enabled.is_(True))
            )
            if config is None:
                return None
            running = await session.scalar(
                select(SiteBuildRequest)
                .where(SiteBuildRequest.status == "RUNNING")
                .with_for_update()
            )
            if running is not None:
                if running.lease_expires_at is None or running.lease_expires_at > now:
                    return None
                pending = await session.scalar(
                    select(SiteBuildRequest)
                    .where(SiteBuildRequest.status == "PENDING")
                    .with_for_update()
                )
                if pending is not None:
                    pending.target_revision = max(pending.target_revision, running.target_revision)
                    running.status = "SUPERSEDED"
                    running.last_error = "worker lease expired; a newer request will retry"
                else:
                    running.status = "PENDING"
                    running.started_at = None
                    running.lease_expires_at = None
                    running.next_attempt_at = now
            request = await session.scalar(
                select(SiteBuildRequest)
                .where(
                    SiteBuildRequest.status == "PENDING",
                    SiteBuildRequest.next_attempt_at <= now,
                )
                .order_by(SiteBuildRequest.requested_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if request is None:
                return None
            request.status = "RUNNING"
            request.attempt_count += 1
            request.started_at = now
            request.lease_expires_at = now + timedelta(
                seconds=self.settings.site_build_lease_seconds
            )
            request.last_error = None
            await session.flush()
            return request

    async def _trigger(self, tenant_id: uuid.UUID, request: SiteBuildRequest) -> None:
        async with self.database.global_session() as session:
            tenant = await session.get(Tenant, tenant_id)
        async with self.database.tenant_session(tenant_id) as session:
            config = await session.get(TenantSiteBuildConfig, tenant_id)
        if tenant is None or config is None or not config.enabled:
            await self._trigger_failed(tenant_id, request.id, "build configuration unavailable")
            return
        started = datetime.now(UTC)
        try:
            await self.executor.trigger_build(tenant=tenant, config=config, request=request)
        except Exception as exc:
            await self._trigger_failed(tenant_id, request.id, str(exc))
            logger.warning(
                "site_build_trigger_failed",
                build_request_id=str(request.id),
                tenant_id=str(tenant_id),
                content_revision=request.target_revision,
                status="RETRY_OR_FAILED",
                duration=(datetime.now(UTC) - started).total_seconds(),
            )
            return
        logger.info(
            "site_build_triggered",
            build_request_id=str(request.id),
            tenant_id=str(tenant_id),
            content_revision=request.target_revision,
            status="RUNNING",
            duration=(datetime.now(UTC) - started).total_seconds(),
        )

    async def _trigger_failed(
        self, tenant_id: uuid.UUID, request_id: uuid.UUID, error: str
    ) -> None:
        now = datetime.now(UTC)
        safe_error = error.strip()[:2000] or "build trigger failed"
        async with self.database.tenant_session(tenant_id) as session:
            request = await session.get(SiteBuildRequest, request_id, with_for_update=True)
            if request is None or request.status != "RUNNING":
                return
            newer = await session.scalar(
                select(SiteBuildRequest)
                .where(SiteBuildRequest.status == "PENDING")
                .with_for_update()
            )
            if newer is not None:
                newer.target_revision = max(newer.target_revision, request.target_revision)
                request.status = "SUPERSEDED"
                request.last_error = safe_error
                request.lease_expires_at = None
                return
            if request.attempt_count >= self.settings.site_build_max_attempts:
                request.status = "FAILED"
                request.failed_at = now
                request.last_error = safe_error
                request.lease_expires_at = None
                return
            delay = min(3600, 2 ** max(0, request.attempt_count - 1) * 30)
            request.status = "PENDING"
            request.next_attempt_at = now + timedelta(seconds=delay)
            request.started_at = None
            request.lease_expires_at = None
            request.last_error = safe_error
