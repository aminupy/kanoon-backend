from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.auth.schemas import LoginRequest, RefreshRequest, TokenPair
from app.auth.service import AuthenticationService
from app.core.database import Database
from app.core.errors import ApplicationError
from app.tenancy.context import TenantContext, tenant_context_from_request
from app.tenancy.dependencies import get_database

admin_auth_router = APIRouter(prefix="/api/v1/admin/auth", tags=["admin-auth"])
platform_auth_router = APIRouter(prefix="/api/v1/platform/auth", tags=["platform-auth"])


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@admin_auth_router.post("/login", response_model=TokenPair)
async def tenant_login(
    body: LoginRequest,
    request: Request,
    tenant: TenantContext = Depends(tenant_context_from_request),
    database: Database = Depends(get_database),
) -> TokenPair:
    service = AuthenticationService(request.app.state.settings)
    async with database.global_session() as session:
        user = await service.authenticate_user(
            session,
            email=str(body.email),
            password=body.password,
            client_ip=_client_ip(request),
            platform_only=False,
        )
    if user is None:
        raise ApplicationError("INVALID_CREDENTIALS", "Invalid email or password.", status_code=401)
    async with database.tenant_session(tenant.tenant_id) as session:
        await service.ensure_tenant_access(session, user=user, tenant_id=tenant.tenant_id)
    async with database.global_session() as session:
        return await service.issue_pair(session, user=user, tenant_id=tenant.tenant_id)


@admin_auth_router.post("/refresh", response_model=TokenPair)
async def tenant_refresh(
    body: RefreshRequest,
    request: Request,
    tenant: TenantContext = Depends(tenant_context_from_request),
    database: Database = Depends(get_database),
) -> TokenPair:
    service = AuthenticationService(request.app.state.settings)
    async with database.global_session() as session:
        pair, reused = await service.rotate_refresh_token(
            session, raw_token=body.refresh_token, expected_tenant_id=tenant.tenant_id
        )
    if reused:
        raise ApplicationError(
            "REFRESH_TOKEN_REUSE_DETECTED",
            "Refresh token reuse was detected; the token family was revoked.",
            status_code=401,
        )
    assert pair is not None
    return pair


@platform_auth_router.post("/login", response_model=TokenPair)
async def platform_login(
    body: LoginRequest,
    request: Request,
    database: Database = Depends(get_database),
) -> TokenPair:
    service = AuthenticationService(request.app.state.settings)
    async with database.global_session() as session:
        user = await service.authenticate_user(
            session,
            email=str(body.email),
            password=body.password,
            client_ip=_client_ip(request),
            platform_only=True,
        )
        if user is None:
            # Commit the failed-attempt record before returning the generic error.
            pass
        else:
            return await service.issue_pair(session, user=user, tenant_id=None)
    raise ApplicationError("INVALID_CREDENTIALS", "Invalid email or password.", status_code=401)


@platform_auth_router.post("/refresh", response_model=TokenPair)
async def platform_refresh(
    body: RefreshRequest,
    request: Request,
    database: Database = Depends(get_database),
) -> TokenPair:
    service = AuthenticationService(request.app.state.settings)
    async with database.global_session() as session:
        pair, reused = await service.rotate_refresh_token(
            session, raw_token=body.refresh_token, expected_tenant_id=None
        )
    if reused:
        raise ApplicationError(
            "REFRESH_TOKEN_REUSE_DETECTED",
            "Refresh token reuse was detected; the token family was revoked.",
            status_code=401,
        )
    assert pair is not None
    return pair
