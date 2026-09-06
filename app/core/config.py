from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="KANOON_",
        case_sensitive=False,
        extra="ignore",
    )

    environment: Literal["development", "testing", "production"] = "development"
    debug: bool = False
    database_dsn: SecretStr = SecretStr(
        "postgresql+psycopg://kanoon_owner:kanoon_owner@localhost:5432/kanoon"
    )
    database_application_role: str = "kanoon_app"
    database_pool_size: int = Field(default=10, ge=1, le=100)
    database_max_overflow: int = Field(default=20, ge=0, le=200)

    signing_key: SecretStr = SecretStr("development-only-change-me-at-least-32-bytes")
    access_token_ttl_seconds: int = Field(default=900, ge=60, le=3600)
    refresh_token_ttl_seconds: int = Field(default=2_592_000, ge=3600)
    draft_token_ttl_seconds: int = Field(default=2_592_000, ge=3600)
    callback_token_ttl_seconds: int = Field(default=900, ge=60, le=3600)
    authentication_window_seconds: int = Field(default=900, ge=60, le=3600)
    authentication_max_attempts: int = Field(default=10, ge=3, le=100)

    trust_forwarded_host: bool = False
    trusted_proxy_cidrs: list[str] = Field(default_factory=list)
    allowed_cors_origins: list[str] = Field(default_factory=list)

    data_plane_host: str = Field(
        default="0.0.0.0",  # noqa: S104 - the data plane is proxy-facing by design
        min_length=1,
        max_length=253,
    )
    data_plane_port: int = Field(default=8000, ge=1, le=65535)
    control_plane_host: str = Field(default="127.0.0.1", min_length=1, max_length=253)
    control_plane_port: int = Field(default=8001, ge=1, le=65535)

    otp_provider: Literal["mock", "external"] = "mock"
    otp_ttl_seconds: int = Field(default=180, ge=60, le=600)
    otp_resend_cooldown_seconds: int = Field(default=60, ge=10, le=600)
    otp_max_attempts: int = Field(default=5, ge=1, le=10)
    otp_max_active_challenges: int = Field(default=3, ge=1, le=10)
    otp_phone_hourly_limit: int = Field(default=10, ge=1, le=100)
    otp_ip_hourly_limit: int = Field(default=20, ge=1, le=500)
    otp_tenant_minute_limit: int = Field(default=100, ge=1, le=10_000)

    payment_provider: Literal["mock", "external"] = "mock"
    public_base_url: str = "http://localhost:8000"

    site_build_webhook_url: str | None = None
    site_build_hmac_secret: SecretStr = SecretStr("development-site-build-secret-change-me")
    site_build_webhook_timeout_seconds: int = Field(default=15, ge=1, le=120)
    site_build_callback_max_age_seconds: int = Field(default=300, ge=30, le=3600)
    site_build_max_attempts: int = Field(default=5, ge=1, le=20)
    site_build_lease_seconds: int = Field(default=300, ge=30, le=3600)
    site_build_poll_seconds: float = Field(default=5.0, ge=0.1, le=300)

    # Internal service endpoint for trusted backend operations.
    s3_endpoint_url: str = "http://localhost:8333"
    # Browser-reachable endpoint used to construct and sign presigned URLs.
    s3_public_endpoint_url: str | None = None
    s3_region: str = "us-east-1"
    s3_bucket: str = "kanoon"
    s3_access_key: SecretStr = SecretStr("development-access-key")
    s3_secret_key: SecretStr = SecretStr("development-secret-key")
    s3_presign_ttl_seconds: int = Field(default=900, ge=60, le=86400)
    upload_max_bytes: int = Field(default=20 * 1024 * 1024, ge=1024)
    upload_allowed_mime_types: list[str] = Field(
        default_factory=lambda: [
            "image/jpeg",
            "image/png",
            "image/webp",
            "application/pdf",
        ]
    )

    @field_validator("s3_endpoint_url", "s3_public_endpoint_url")
    @classmethod
    def validate_s3_endpoint_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
            raise ValueError("S3 endpoint URLs must be absolute HTTP(S) URLs")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("S3 endpoint URLs must not contain credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("S3 endpoint URLs must not contain a query or fragment")
        return value.rstrip("/")

    @model_validator(mode="after")
    def reject_unsafe_production_settings(self) -> Settings:
        if self.environment == "production":
            # if self.otp_provider == "mock" or self.payment_provider == "mock":
            #     raise ValueError("mock OTP/payment providers are forbidden in production")
            if len(self.signing_key.get_secret_value()) < 32:
                raise ValueError("production signing key must contain at least 32 characters")
            if len(self.site_build_hmac_secret.get_secret_value()) < 32:
                raise ValueError("production site-build HMAC secret must contain 32 characters")
            if self.debug:
                raise ValueError("debug mode is forbidden in production")
        if self.trust_forwarded_host and not self.trusted_proxy_cidrs:
            raise ValueError("trusted proxy CIDRs are required when forwarded hosts are trusted")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
