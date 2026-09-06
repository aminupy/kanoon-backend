from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any, Literal, Protocol
from urllib.parse import quote, urlsplit

import anyio
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

if TYPE_CHECKING:
    from types_boto3_s3 import S3Client
else:
    S3Client = Any

from app.core.config import Settings

S3_CLIENT_CONFIG = Config(
    signature_version="s3v4",
    s3={"addressing_style": "path"},
)


@dataclass(frozen=True, slots=True)
class PresignedUpload:
    url: str
    fields: dict[str, str]


@dataclass(frozen=True, slots=True)
class StoredObject:
    size_bytes: int
    content_type: str
    metadata: dict[str, str]


class ObjectStorage(Protocol):
    async def ensure_bucket(self) -> None: ...

    async def healthcheck(self) -> None: ...

    async def presign_upload(
        self, *, object_key: str, mime_type: str, max_bytes: int
    ) -> PresignedUpload: ...

    async def inspect(self, *, object_key: str) -> StoredObject | None: ...

    async def presign_download(
        self,
        *,
        object_key: str,
        filename: str,
        disposition: Literal["attachment", "inline"] = "attachment",
    ) -> str: ...

    async def delete(self, *, object_key: str) -> None: ...


class S3ObjectStorage:
    def __init__(self, settings: Settings) -> None:
        if settings.environment == "production":
            if settings.s3_public_endpoint_url is None:
                raise ValueError("a public S3 endpoint URL is required in production")
            if urlsplit(settings.s3_public_endpoint_url).scheme != "https":
                raise ValueError("the production public S3 endpoint URL must use HTTPS")
        self.settings = settings
        self.client: S3Client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key.get_secret_value(),
            aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
            config=S3_CLIENT_CONFIG,
        )
        public_endpoint = settings.s3_public_endpoint_url or settings.s3_endpoint_url
        self.presign_client: S3Client
        if public_endpoint == settings.s3_endpoint_url:
            self.presign_client = self.client
        else:
            self.presign_client = boto3.client(
                "s3",
                endpoint_url=public_endpoint,
                region_name=settings.s3_region,
                aws_access_key_id=settings.s3_access_key.get_secret_value(),
                aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
                config=S3_CLIENT_CONFIG,
            )

    async def ensure_bucket(self) -> None:
        try:
            await self.healthcheck()
        except ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code", ""))
            if error_code not in {"404", "NoSuchBucket", "NotFound"}:
                raise
            await anyio.to_thread.run_sync(
                partial(self.client.create_bucket, Bucket=self.settings.s3_bucket)
            )

    async def healthcheck(self) -> None:
        await anyio.to_thread.run_sync(
            partial(self.client.head_bucket, Bucket=self.settings.s3_bucket)
        )

    async def presign_upload(
        self, *, object_key: str, mime_type: str, max_bytes: int
    ) -> PresignedUpload:
        operation = partial(
            self.presign_client.generate_presigned_post,
            Bucket=self.settings.s3_bucket,
            Key=object_key,
            Fields={"Content-Type": mime_type},
            Conditions=[
                {"Content-Type": mime_type},
                ["content-length-range", 1, max_bytes],
            ],
            ExpiresIn=self.settings.s3_presign_ttl_seconds,
        )
        result = await anyio.to_thread.run_sync(operation)
        return PresignedUpload(url=result["url"], fields=result["fields"])

    async def inspect(self, *, object_key: str) -> StoredObject | None:
        try:
            result = await anyio.to_thread.run_sync(
                partial(
                    self.client.head_object,
                    Bucket=self.settings.s3_bucket,
                    Key=object_key,
                )
            )
        except ClientError as exc:
            error = exc.response.get("Error", {})
            error_code = str(error.get("Code", ""))
            response_metadata = exc.response.get("ResponseMetadata", {})
            http_status = response_metadata.get("HTTPStatusCode")
            if error_code in {"404", "NoSuchKey", "NotFound"} or http_status == 404:
                return None
            raise
        return StoredObject(
            size_bytes=result["ContentLength"],
            content_type=result.get("ContentType", "application/octet-stream"),
            metadata=result.get("Metadata", {}),
        )

    async def presign_download(
        self,
        *,
        object_key: str,
        filename: str,
        disposition: Literal["attachment", "inline"] = "attachment",
    ) -> str:
        return await anyio.to_thread.run_sync(
            partial(
                self.presign_client.generate_presigned_url,
                "get_object",
                Params={
                    "Bucket": self.settings.s3_bucket,
                    "Key": object_key,
                    "ResponseContentDisposition": (
                        f"{disposition}; filename*=UTF-8''{quote(filename, safe='')}"
                    ),
                },
                ExpiresIn=self.settings.s3_presign_ttl_seconds,
            )
        )

    async def delete(self, *, object_key: str) -> None:
        await anyio.to_thread.run_sync(
            partial(
                self.client.delete_object,
                Bucket=self.settings.s3_bucket,
                Key=object_key,
            )
        )
