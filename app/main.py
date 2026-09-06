from __future__ import annotations

from fastapi import FastAPI

from app.application import create_base_app, install_common_middleware
from app.auth.router import admin_auth_router
from app.blog.admin_router import router as admin_blog_router
from app.blog.public_router import router as public_blog_router
from app.content.admin_router import router as admin_content_router
from app.content.public_router import router as public_content_router
from app.core.config import Settings, get_settings
from app.core.http_security import DynamicCORSMiddleware
from app.core.openapi import install_openapi_contract
from app.media.router import admin_router as admin_media_router
from app.media.router import public_router as public_media_router
from app.media.storage import ObjectStorage, S3ObjectStorage
from app.otp.provider import MockOTPProvider, OTPProvider
from app.payments.provider import MockPaymentGateway, PaymentGateway
from app.payments.router import callback_router, registration_payment_router
from app.registrations.admin_router import router as admin_registrations_router
from app.registrations.router import router as registrations_router
from app.site_builds.admin_router import router as admin_site_build_router
from app.site_builds.internal_router import router as internal_site_build_router
from app.tenancy.middleware import TenantResolutionMiddleware


def create_app(
    settings: Settings | None = None,
    *,
    otp_provider: OTPProvider | None = None,
    payment_gateway: PaymentGateway | None = None,
    object_storage: ObjectStorage | None = None,
) -> FastAPI:
    configured = settings or get_settings()
    if otp_provider is None:
        if configured.otp_provider != "mock":
            raise RuntimeError("an external OTPProvider adapter must be supplied")
        otp_provider = MockOTPProvider()
    if payment_gateway is None:
        if configured.payment_provider != "mock":
            raise RuntimeError("an external PaymentGateway adapter must be supplied")
        payment_gateway = MockPaymentGateway()
    if object_storage is None:
        object_storage = S3ObjectStorage(configured)

    startup_checks = (
        (object_storage.ensure_bucket,) if configured.environment != "production" else ()
    )
    app, database = create_base_app(
        configured,
        title="Kanoon Educational Institute API",
        description="Domain-resolved, RLS-protected multi-tenant backend.",
        docs_url="/docs" if configured.environment != "production" else None,
        startup_checks=startup_checks,
        readiness_checks=(object_storage.healthcheck,),
    )
    app.state.otp_provider = otp_provider
    app.state.payment_gateway = payment_gateway
    app.state.object_storage = object_storage
    app.add_middleware(
        DynamicCORSMiddleware,
        database=database,
        settings=configured,
    )
    app.add_middleware(
        TenantResolutionMiddleware,
        database=database,
        settings=configured,
    )
    install_common_middleware(app)
    app.include_router(admin_auth_router)
    app.include_router(registrations_router)
    app.include_router(registration_payment_router)
    app.include_router(callback_router)
    app.include_router(admin_media_router)
    app.include_router(public_media_router)
    app.include_router(public_blog_router)
    app.include_router(public_content_router)
    app.include_router(admin_blog_router)
    app.include_router(admin_content_router)
    app.include_router(admin_site_build_router)
    app.include_router(admin_registrations_router)
    app.include_router(internal_site_build_router)
    install_openapi_contract(app)

    return app


app = create_app()
