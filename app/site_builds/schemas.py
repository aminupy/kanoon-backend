from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SiteBuildStatus(BaseModel):
    current_content_revision: int
    deployed_revision: int | None
    state: Literal["UP_TO_DATE", "PENDING", "BUILDING", "FAILED", "NOT_CONFIGURED"]
    latest_request_id: uuid.UUID | None
    latest_status: str | None
    latest_target_revision: int | None
    latest_failure: str | None
    requested_at: datetime | None
    completed_at: datetime | None


class SiteBuildHistoryItem(BaseModel):
    id: uuid.UUID
    reason: str
    target_revision: int
    actual_revision: int | None
    status: str
    attempt_count: int
    requested_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    failed_at: datetime | None
    last_error: str | None


class BuildConfigWrite(BaseModel):
    enabled: bool = False
    canonical_domain: str = Field(pattern=r"^[a-z0-9.-]+$", max_length=253)
    build_target_key: str = Field(pattern=r"^[A-Za-z0-9._:-]+$", max_length=200)
    deployment_target_key: str = Field(pattern=r"^[A-Za-z0-9._:-]+$", max_length=200)


class BuildConfigResponse(BuildConfigWrite):
    tenant_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class BuildResult(BaseModel):
    tenant_id: uuid.UUID
    status: Literal["SUCCESSFUL", "FAILED"]
    actual_revision: int | None = Field(default=None, ge=0)
    error: str | None = Field(default=None, max_length=2000)
    retryable: bool = True
