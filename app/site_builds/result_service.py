from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.site_builds.models import SiteBuildRequest
from app.site_builds.schemas import BuildResult
from app.site_builds.service import SiteBuildService


class BuildResultService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def record(
        self,
        session: AsyncSession,
        *,
        request_id: uuid.UUID,
        result: BuildResult,
    ) -> SiteBuildRequest:
        request = await session.get(SiteBuildRequest, request_id, with_for_update=True)
        if request is None or request.tenant_id != result.tenant_id:
            raise ApplicationError(
                "BUILD_REQUEST_NOT_FOUND", "Build request was not found.", status_code=404
            )
        now = datetime.now(UTC)
        if result.status == "SUCCESSFUL":
            if result.actual_revision is None or result.actual_revision < request.target_revision:
                raise ApplicationError(
                    "BUILD_REVISION_INVALID",
                    "The deployed revision is older than the requested revision.",
                    status_code=422,
                )
            if request.status == "SUCCESSFUL":
                if request.actual_revision != result.actual_revision:
                    raise ApplicationError(
                        "BUILD_RESULT_CONFLICT",
                        "Build result conflicts with the recorded result.",
                        status_code=409,
                    )
                return request
            if request.status == "SUPERSEDED" and request.completed_at is not None:
                if request.actual_revision != result.actual_revision:
                    raise ApplicationError(
                        "BUILD_RESULT_CONFLICT",
                        "Build result conflicts with the recorded result.",
                        status_code=409,
                    )
                return request
            if request.status == "FAILED":
                raise ApplicationError(
                    "BUILD_RESULT_CONFLICT",
                    "Build result conflicts with the recorded result.",
                    status_code=409,
                )
            state = await SiteBuildService().state_for_update(session, result.tenant_id)
            previous = state.last_successful_build_revision
            state.last_successful_build_revision = max(previous or 0, result.actual_revision)
            state.last_build_at = now
            if request.status != "SUPERSEDED":
                request.status = "SUCCESSFUL"
            request.actual_revision = result.actual_revision
            request.completed_at = now
            request.lease_expires_at = None
            request.last_error = None
            await session.flush()
            return request
        if request.status in {"SUCCESSFUL", "SUPERSEDED", "FAILED"}:
            return request
        newer = await session.scalar(
            select(SiteBuildRequest).where(SiteBuildRequest.status == "PENDING").with_for_update()
        )
        if newer is not None:
            newer.target_revision = max(newer.target_revision, request.target_revision)
            request.status = "SUPERSEDED"
        elif result.retryable and request.attempt_count < self.settings.site_build_max_attempts:
            delay = min(3600, 2 ** max(0, request.attempt_count - 1) * 30)
            request.status = "PENDING"
            request.next_attempt_at = now + timedelta(seconds=delay)
            request.started_at = None
        else:
            request.status = "FAILED"
            request.failed_at = now
        request.lease_expires_at = None
        request.last_error = (result.error or "build failed").strip()[:2000]
        await session.flush()
        return request
