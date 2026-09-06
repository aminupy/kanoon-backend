from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from functools import partial
from urllib.parse import parse_qs, urlsplit

import anyio
import httpx
import pytest
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.main import create_app
from app.media.models import MediaAsset
from app.media.storage import S3ObjectStorage
from app.tenancy.models import Tenant, TenantDomain

pytestmark = pytest.mark.integration

# Deterministic 1x1 transparent PNG.
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010804000000b51c0c02"
    "0000000b4944415478da63fcff1f0003030200ee56e75f0000000049454e44ae426082"
)


async def test_real_s3_presigned_upload_inspect_download_and_cleanup() -> None:
    endpoint = os.getenv("KANOON_TEST_S3_ENDPOINT_URL")
    if endpoint is None:
        pytest.skip("KANOON_TEST_S3_ENDPOINT_URL is required for the real S3 adapter gate")
    settings = Settings(
        environment="testing",
        s3_endpoint_url=endpoint,
        s3_public_endpoint_url=endpoint,
        s3_bucket=f"kanoon-test-{uuid.uuid4().hex}",
    )
    storage = S3ObjectStorage(settings)
    object_key = f"tests/{uuid.uuid4()}/fixture.png"
    await storage.ensure_bucket()
    try:
        upload = await storage.presign_upload(
            object_key=object_key,
            mime_type="image/png",
            max_bytes=1024,
        )
        assert upload.fields["x-amz-algorithm"] == "AWS4-HMAC-SHA256"
        assert "AWSAccessKeyId" not in upload.fields
        async with httpx.AsyncClient(follow_redirects=False) as client:
            uploaded = await client.post(
                upload.url,
                data=upload.fields,
                files={"file": ("fixture.png", PNG_BYTES, "image/png")},
            )
            assert uploaded.status_code in {200, 204}

            stored = await storage.inspect(object_key=object_key)
            assert stored is not None
            assert stored.size_bytes == len(PNG_BYTES)
            assert stored.content_type == "image/png"

            signed_download = await storage.presign_download(
                object_key=object_key,
                filename="fixture.png",
                disposition="inline",
            )
            download_query = parse_qs(urlsplit(signed_download).query)
            assert download_query["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
            assert download_query["X-Amz-SignedHeaders"] == ["host"]
            assert "AWSAccessKeyId" not in download_query
            downloaded = await client.get(signed_download)
            assert downloaded.status_code == 200
            assert downloaded.content == PNG_BYTES
            assert downloaded.headers["content-type"].split(";", 1)[0] == "image/png"
    finally:
        await storage.delete(object_key=object_key)
        await anyio.to_thread.run_sync(
            partial(storage.client.delete_bucket, Bucket=settings.s3_bucket)
        )

    assert await storage.inspect(object_key=object_key) is None


async def test_public_media_redirect_returns_exact_bytes_while_private_media_stays_private(
    owner_engine: AsyncEngine,
) -> None:
    endpoint = os.getenv("KANOON_TEST_S3_ENDPOINT_URL")
    if endpoint is None:
        pytest.skip("KANOON_TEST_S3_ENDPOINT_URL is required for the real S3 adapter gate")
    tenant_id = uuid.uuid4()
    public_media_id = uuid.uuid4()
    private_media_id = uuid.uuid4()
    host = f"media-{tenant_id}.example.test"
    settings = Settings(
        environment="testing",
        s3_endpoint_url=endpoint,
        s3_public_endpoint_url=endpoint,
        s3_bucket=f"kanoon-test-{uuid.uuid4().hex}",
        database_dsn=os.environ["KANOON_TEST_DATABASE_DSN"],
        database_pool_size=1,
        database_max_overflow=0,
    )
    storage = S3ObjectStorage(settings)
    object_keys = {
        public_media_id: f"tenants/{tenant_id}/{public_media_id}/public.png",
        private_media_id: f"tenants/{tenant_id}/{private_media_id}/private.png",
    }
    await storage.ensure_bucket()
    app = create_app(settings, object_storage=storage)
    try:
        async with httpx.AsyncClient() as storage_client:
            for object_key in object_keys.values():
                upload = await storage.presign_upload(
                    object_key=object_key,
                    mime_type="image/png",
                    max_bytes=1024,
                )
                uploaded = await storage_client.post(
                    upload.url,
                    data=upload.fields,
                    files={"file": ("fixture.png", PNG_BYTES, "image/png")},
                )
                assert uploaded.status_code in {200, 204}

        async with owner_engine.begin() as connection:
            await connection.execute(
                insert(Tenant),
                {
                    "id": tenant_id,
                    "name": "Media redirect tenant",
                    "slug": f"media-{tenant_id}",
                    "status": "ACTIVE",
                    "default_locale": "fa-IR",
                    "timezone": "Asia/Tehran",
                    "default_currency": "IRR",
                },
            )
            await connection.execute(
                insert(TenantDomain),
                {
                    "tenant_id": tenant_id,
                    "hostname": host,
                    "is_primary": True,
                    "is_active": True,
                    "created_at": datetime.now(UTC),
                },
            )
            await connection.execute(
                insert(MediaAsset),
                [
                    {
                        "id": public_media_id,
                        "tenant_id": tenant_id,
                        "object_key": object_keys[public_media_id],
                        "original_filename": "public.png",
                        "mime_type": "image/png",
                        "size_bytes": len(PNG_BYTES),
                        "status": "READY",
                        "visibility": "PUBLIC",
                    },
                    {
                        "id": private_media_id,
                        "tenant_id": tenant_id,
                        "object_key": object_keys[private_media_id],
                        "original_filename": "private.png",
                        "mime_type": "image/png",
                        "size_bytes": len(PNG_BYTES),
                        "status": "READY",
                        "visibility": "PRIVATE",
                    },
                ],
            )

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as api_client:
            public = await api_client.get(
                f"/api/v1/public/media/{public_media_id}", headers={"Host": host}
            )
            private = await api_client.get(
                f"/api/v1/public/media/{private_media_id}", headers={"Host": host}
            )
        assert public.status_code == 307
        assert private.status_code == 404
        async with httpx.AsyncClient() as storage_client:
            downloaded = await storage_client.get(public.headers["location"])
        assert downloaded.status_code == 200
        assert downloaded.content == PNG_BYTES
        assert downloaded.headers["content-type"].split(";", 1)[0] == "image/png"
    finally:
        await app.state.database.dispose()
        for object_key in object_keys.values():
            await storage.delete(object_key=object_key)
        await anyio.to_thread.run_sync(
            partial(storage.client.delete_bucket, Bucket=settings.s3_bucket)
        )
