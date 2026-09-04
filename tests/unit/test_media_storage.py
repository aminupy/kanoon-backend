from urllib.parse import urlsplit

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.media.storage import S3ObjectStorage


async def test_presigned_urls_use_public_endpoint_while_operations_use_internal_endpoint() -> None:
    settings = Settings(
        environment="testing",
        s3_endpoint_url="http://storage.internal:8333",
        s3_public_endpoint_url="https://storage.example.com",
        s3_bucket="kanoon",
        s3_access_key="test-access-key",
        s3_secret_key="test-secret-key",
    )
    storage = S3ObjectStorage(settings)

    upload = await storage.presign_upload(
        object_key="tenants/tenant-id/media-id/image.webp",
        mime_type="image/webp",
        max_bytes=1024,
    )
    download = await storage.presign_download(
        object_key="tenants/tenant-id/media-id/image.webp",
        filename="image.webp",
        disposition="inline",
    )

    assert storage.client.meta.endpoint_url == "http://storage.internal:8333"
    assert storage.presign_client.meta.endpoint_url == "https://storage.example.com"
    assert urlsplit(upload.url).scheme == "https"
    assert urlsplit(upload.url).netloc == "storage.example.com"
    assert urlsplit(download).scheme == "https"
    assert urlsplit(download).netloc == "storage.example.com"
    assert "storage.internal" not in upload.url
    assert "storage.internal" not in download


async def test_presigning_falls_back_to_internal_endpoint_outside_production() -> None:
    settings = Settings(
        environment="testing",
        s3_endpoint_url="http://localhost:8333",
        s3_public_endpoint_url=None,
    )
    storage = S3ObjectStorage(settings)

    upload = await storage.presign_upload(
        object_key="tenants/tenant-id/media-id/image.png",
        mime_type="image/png",
        max_bytes=1024,
    )

    assert storage.presign_client is storage.client
    assert urlsplit(upload.url).netloc == "localhost:8333"


def test_production_requires_https_public_s3_endpoint() -> None:
    with pytest.raises(ValueError, match="public S3 endpoint URL is required"):
        S3ObjectStorage(
            Settings(
                environment="production",
                otp_provider="external",
                payment_provider="external",
                signing_key="s" * 64,
                site_build_hmac_secret="h" * 64,
            )
        )
    with pytest.raises(ValueError, match="public S3 endpoint URL must use HTTPS"):
        S3ObjectStorage(
            Settings(
                environment="production",
                otp_provider="external",
                payment_provider="external",
                signing_key="s" * 64,
                site_build_hmac_secret="h" * 64,
                s3_public_endpoint_url="http://storage.example.com",
            )
        )


@pytest.mark.parametrize(
    "endpoint",
    [
        "storage.example.com",
        "ftp://storage.example.com",
        "https://user:password@storage.example.com",
        "https://storage.example.com?secret=value",
        "https://storage.example.com/#fragment",
    ],
)
def test_s3_endpoints_reject_malformed_or_secret_bearing_urls(endpoint: str) -> None:
    with pytest.raises(ValidationError):
        Settings(s3_public_endpoint_url=endpoint)
