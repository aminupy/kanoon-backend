from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

import httpx

from app.core.config import Settings
from app.site_builds.models import SiteBuildRequest, TenantSiteBuildConfig
from app.site_builds.signing import sign_message
from app.tenancy.models import Tenant


class SiteBuildExecutor(Protocol):
    async def trigger_build(
        self,
        *,
        tenant: Tenant,
        config: TenantSiteBuildConfig,
        request: SiteBuildRequest,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class TriggeredBuild:
    tenant_id: uuid.UUID
    build_request_id: uuid.UUID
    target_revision: int


class FakeSiteBuildExecutor:
    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.triggered: list[TriggeredBuild] = []

    async def trigger_build(
        self,
        *,
        tenant: Tenant,
        config: TenantSiteBuildConfig,
        request: SiteBuildRequest,
    ) -> None:
        del config
        self.triggered.append(
            TriggeredBuild(
                tenant_id=tenant.id,
                build_request_id=request.id,
                target_revision=request.target_revision,
            )
        )
        if self.failures > 0:
            self.failures -= 1
            raise RuntimeError("simulated transient build trigger failure")


class WebhookSiteBuildExecutor:
    def __init__(self, settings: Settings) -> None:
        if not settings.site_build_webhook_url:
            raise RuntimeError("KANOON_SITE_BUILD_WEBHOOK_URL must be configured")
        self.settings = settings

    async def trigger_build(
        self,
        *,
        tenant: Tenant,
        config: TenantSiteBuildConfig,
        request: SiteBuildRequest,
    ) -> None:
        url = self.settings.site_build_webhook_url
        if url is None:  # pragma: no cover - constructor invariant
            raise RuntimeError("site build webhook is not configured")
        callback_url = (
            f"{self.settings.public_base_url.rstrip('/')}/api/v1/internal/site-builds/"
            f"{request.id}/result"
        )
        payload = {
            "schema_version": 1,
            "build_request_id": str(request.id),
            "tenant_id": str(tenant.id),
            "tenant_slug": tenant.slug,
            "canonical_domain": config.canonical_domain,
            "build_target_key": config.build_target_key,
            "deployment_target_key": config.deployment_target_key,
            "target_revision": request.target_revision,
            "snapshot_path": (
                f"/api/v1/public/blog/snapshot?requested_revision={request.target_revision}"
            ),
            "callback_url": callback_url,
        }
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        timestamp = int(time.time())
        parsed = urlsplit(url)
        signed_path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        signature = sign_message(
            self.settings.site_build_hmac_secret.get_secret_value(),
            timestamp,
            "POST",
            signed_path,
            body,
        )
        async with httpx.AsyncClient(
            timeout=self.settings.site_build_webhook_timeout_seconds
        ) as client:
            response = await client.post(
                url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Kanoon-Timestamp": str(timestamp),
                    "X-Kanoon-Signature": signature,
                    "Idempotency-Key": str(request.id),
                },
            )
        response.raise_for_status()
