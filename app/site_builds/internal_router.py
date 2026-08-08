from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Header, Request
from pydantic import ValidationError

from app.core.errors import ApplicationError
from app.site_builds.result_service import BuildResultService
from app.site_builds.schemas import BuildResult
from app.site_builds.signing import verify_message

router = APIRouter(prefix="/api/v1/internal/site-builds", tags=["internal-site-builds"])
logger = structlog.get_logger(__name__)


@router.post(
    "/{request_id}/result",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": BuildResult.model_json_schema()}},
        }
    },
)
async def record_build_result(
    request_id: uuid.UUID,
    request: Request,
    timestamp: str | None = Header(default=None, alias="X-Kanoon-Timestamp"),
    signature: str | None = Header(default=None, alias="X-Kanoon-Signature"),
) -> dict[str, str]:
    started = datetime.now(UTC)
    settings = request.app.state.settings
    raw_body = await request.body()
    verify_message(
        secret=settings.site_build_hmac_secret.get_secret_value(),
        timestamp_value=timestamp,
        signature=signature,
        method=request.method,
        path=request.url.path,
        body=raw_body,
        max_age_seconds=settings.site_build_callback_max_age_seconds,
    )
    try:
        body = BuildResult.model_validate_json(raw_body)
    except ValidationError as exc:
        raise ApplicationError(
            "BUILD_RESULT_INVALID", "Build result is invalid.", status_code=422
        ) from exc
    database = request.app.state.database
    async with database.tenant_session(body.tenant_id) as session:
        build_request = await BuildResultService(settings).record(
            session, request_id=request_id, result=body
        )
    if build_request.tenant_id != body.tenant_id:  # pragma: no cover - service invariant
        raise ApplicationError(
            "BUILD_REQUEST_NOT_FOUND", "Build request was not found.", status_code=404
        )
    logger.info(
        "site_build_result_recorded",
        build_request_id=str(build_request.id),
        tenant_id=str(build_request.tenant_id),
        content_revision=build_request.actual_revision or build_request.target_revision,
        status=build_request.status,
        duration=(datetime.now(UTC) - started).total_seconds(),
    )
    return {"status": "accepted"}
