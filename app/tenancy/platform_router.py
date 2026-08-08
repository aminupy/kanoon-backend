from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError

from app.audit.models import AuditEvent
from app.auth.dependencies import Principal, platform_principal
from app.auth.models import TenantMembership, User
from app.auth.security import hash_password
from app.core.database import Database
from app.core.errors import ApplicationError
from app.site_builds.models import TenantSiteBuildConfig
from app.site_builds.schemas import BuildConfigResponse, BuildConfigWrite
from app.tenancy.dependencies import get_database
from app.tenancy.features import FEATURE_KEYS, validate_feature_key
from app.tenancy.models import Tenant, TenantDomain, TenantFeature
from app.tenancy.schemas import (
    DomainCreate,
    DomainResponse,
    FeatureResponse,
    FeatureUpdate,
    MembershipCreate,
    TenantCreate,
    TenantStatusUpdate,
    TenantSummary,
)

router = APIRouter(
    prefix="/api/v1/platform/tenants",
    tags=["platform-tenants"],
    dependencies=[Depends(platform_principal)],
)


async def _require_tenant(database: Database, tenant_id: uuid.UUID) -> Tenant:
    async with database.global_session() as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            raise ApplicationError("TENANT_NOT_FOUND", "Tenant was not found.", status_code=404)
        return tenant


@router.get("", response_model=list[TenantSummary])
async def list_tenants(database: Database = Depends(get_database)) -> list[Tenant]:
    async with database.global_session() as session:
        return list((await session.scalars(select(Tenant).order_by(Tenant.created_at))).all())


@router.post("", response_model=TenantSummary, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    body: TenantCreate,
    database: Database = Depends(get_database),
) -> Tenant:
    if (body.first_admin_email is None) != (body.first_admin_password is None):
        raise ApplicationError(
            "FIRST_ADMIN_INCOMPLETE",
            "First administrator email and password must be supplied together.",
        )
    now = datetime.now(UTC)
    tenant = Tenant(
        name=body.name,
        slug=body.slug,
        status="ACTIVE",
        default_locale=body.default_locale,
        timezone=body.timezone,
        default_currency=body.default_currency.upper(),
    )
    try:
        async with database.global_session() as session:
            session.add(tenant)
            await session.flush()
            session.add(
                TenantDomain(
                    tenant_id=tenant.id,
                    hostname=body.primary_hostname,
                    is_primary=True,
                    is_active=True,
                    created_at=now,
                )
            )
            await session.execute(
                text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
                {"tenant_id": str(tenant.id)},
            )
            session.add_all(
                TenantFeature(
                    tenant_id=tenant.id,
                    feature_key=key,
                    enabled=True,
                    configuration={},
                )
                for key in FEATURE_KEYS
            )
            if body.first_admin_email and body.first_admin_password:
                normalized_email = str(body.first_admin_email).casefold()
                user = await session.scalar(select(User).where(User.email == normalized_email))
                if user is None:
                    user = User(
                        email=normalized_email,
                        password_hash=hash_password(body.first_admin_password),
                        is_active=True,
                        is_platform_admin=False,
                    )
                    session.add(user)
                    await session.flush()
                session.add(
                    TenantMembership(
                        tenant_id=tenant.id,
                        user_id=user.id,
                        role="TENANT_ADMIN",
                        created_at=now,
                    )
                )
    except IntegrityError as exc:
        raise ApplicationError(
            "TENANT_CONFLICT",
            "Tenant slug, domain, or administrator already exists.",
            status_code=409,
        ) from exc
    return tenant


@router.patch("/{tenant_id}/status", response_model=TenantSummary)
async def set_tenant_status(
    tenant_id: uuid.UUID,
    body: TenantStatusUpdate,
    database: Database = Depends(get_database),
) -> Tenant:
    tenant = await _require_tenant(database, tenant_id)
    async with database.global_session() as session:
        managed = await session.merge(tenant)
        managed.status = body.status.value
        await session.flush()
        return managed


@router.post("/{tenant_id}/domains", response_model=DomainResponse, status_code=201)
async def add_domain(
    tenant_id: uuid.UUID,
    body: DomainCreate,
    database: Database = Depends(get_database),
) -> TenantDomain:
    await _require_tenant(database, tenant_id)
    domain = TenantDomain(
        tenant_id=tenant_id,
        hostname=body.hostname,
        is_primary=body.is_primary,
        is_active=True,
        created_at=datetime.now(UTC),
    )
    try:
        async with database.global_session() as session:
            if body.is_primary:
                await session.execute(
                    update(TenantDomain)
                    .where(TenantDomain.tenant_id == tenant_id)
                    .values(is_primary=False)
                )
            session.add(domain)
            await session.flush()
    except IntegrityError as exc:
        raise ApplicationError(
            "DOMAIN_CONFLICT", "Domain is already registered.", status_code=409
        ) from exc
    return domain


@router.put("/{tenant_id}/features/{feature_key}", response_model=FeatureResponse)
async def set_feature(
    tenant_id: uuid.UUID,
    feature_key: str,
    body: FeatureUpdate,
    request: Request,
    principal: Principal = Depends(platform_principal),
    database: Database = Depends(get_database),
) -> FeatureResponse:
    del request
    try:
        validate_feature_key(feature_key)
    except ValueError as exc:
        raise ApplicationError(
            "UNKNOWN_FEATURE", "Feature key is not supported.", status_code=422
        ) from exc
    await _require_tenant(database, tenant_id)
    async with database.tenant_session(tenant_id) as session:
        feature = await session.get(TenantFeature, (tenant_id, feature_key))
        if feature is None:
            feature = TenantFeature(
                tenant_id=tenant_id,
                feature_key=feature_key,
                enabled=body.enabled,
                configuration=body.configuration,
            )
            session.add(feature)
        else:
            feature.enabled = body.enabled
            feature.configuration = body.configuration
        session.add(
            AuditEvent(
                tenant_id=tenant_id,
                actor_user_id=principal.user_id,
                action="tenant.feature.updated",
                entity_type="tenant_feature",
                metadata_={"feature_key": feature_key, "enabled": body.enabled},
                created_at=datetime.now(UTC),
            )
        )
        await session.flush()
    return FeatureResponse(
        feature_key=feature_key, enabled=body.enabled, configuration=body.configuration
    )


@router.post("/{tenant_id}/memberships", status_code=201)
async def add_membership(
    tenant_id: uuid.UUID,
    body: MembershipCreate,
    database: Database = Depends(get_database),
) -> dict[str, str]:
    await _require_tenant(database, tenant_id)
    email = str(body.email).casefold()
    now = datetime.now(UTC)
    try:
        async with database.tenant_session(tenant_id) as session:
            user = await session.scalar(select(User).where(User.email == email))
            if user is None:
                if body.password is None:
                    raise ApplicationError(
                        "USER_PASSWORD_REQUIRED", "A password is required for a new identity."
                    )
                user = User(
                    email=email,
                    password_hash=hash_password(body.password),
                    is_active=True,
                    is_platform_admin=False,
                )
                session.add(user)
                await session.flush()
            session.add(
                TenantMembership(
                    tenant_id=tenant_id,
                    user_id=user.id,
                    role=body.role.value,
                    created_at=now,
                )
            )
            await session.flush()
    except IntegrityError as exc:
        raise ApplicationError(
            "MEMBERSHIP_CONFLICT", "The user is already a tenant member.", status_code=409
        ) from exc
    return {"status": "created"}


@router.put("/{tenant_id}/site-build-config", response_model=BuildConfigResponse)
async def set_site_build_config(
    tenant_id: uuid.UUID,
    body: BuildConfigWrite,
    principal: Principal = Depends(platform_principal),
    database: Database = Depends(get_database),
) -> TenantSiteBuildConfig:
    await _require_tenant(database, tenant_id)
    async with database.tenant_session(tenant_id) as session:
        registered_domain = await session.scalar(
            select(TenantDomain.id).where(
                TenantDomain.tenant_id == tenant_id,
                TenantDomain.hostname == body.canonical_domain,
                TenantDomain.is_active.is_(True),
            )
        )
        if registered_domain is None:
            raise ApplicationError(
                "BUILD_DOMAIN_INVALID",
                "The canonical build domain must be an active tenant domain.",
                status_code=422,
            )
        config = await session.get(TenantSiteBuildConfig, tenant_id)
        if config is None:
            config = TenantSiteBuildConfig(tenant_id=tenant_id, **body.model_dump())
            session.add(config)
        else:
            for field, value in body.model_dump().items():
                setattr(config, field, value)
        session.add(
            AuditEvent(
                tenant_id=tenant_id,
                actor_user_id=principal.user_id,
                action="site_build.config_updated",
                entity_type="tenant_site_build_config",
                metadata_={"enabled": body.enabled},
                created_at=datetime.now(UTC),
            )
        )
        await session.flush()
        return config


@router.get("/{tenant_id}/site-build-config", response_model=BuildConfigResponse)
async def get_site_build_config(
    tenant_id: uuid.UUID,
    database: Database = Depends(get_database),
) -> TenantSiteBuildConfig:
    await _require_tenant(database, tenant_id)
    async with database.tenant_session(tenant_id) as session:
        config = await session.get(TenantSiteBuildConfig, tenant_id)
        if config is None:
            raise ApplicationError(
                "BUILD_CONFIG_NOT_FOUND", "Site build configuration was not found.", status_code=404
            )
        return config
