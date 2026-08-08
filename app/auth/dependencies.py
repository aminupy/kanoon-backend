from __future__ import annotations

import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import TenantMembership, TenantRole, User
from app.auth.permissions import Permission, role_has_permission
from app.auth.security import AccessClaims, decode_access_token
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.tenancy.context import TenantContext, tenant_context_from_request
from app.tenancy.dependencies import get_database, tenant_session

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: uuid.UUID
    tenant_id: uuid.UUID | None
    role: TenantRole | None
    is_platform_admin: bool


def _settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


def _claims(credentials: HTTPAuthorizationCredentials | None, settings: Settings) -> AccessClaims:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise ApplicationError(
            "AUTHENTICATION_REQUIRED", "Authentication is required.", status_code=401
        )
    try:
        return decode_access_token(settings, credentials.credentials)
    except (jwt.InvalidTokenError, ValueError) as exc:
        raise ApplicationError(
            "INVALID_ACCESS_TOKEN", "The access token is invalid or expired.", status_code=401
        ) from exc


async def tenant_principal(
    tenant: TenantContext = Depends(tenant_context_from_request),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    settings: Settings = Depends(_settings),
    session: AsyncSession = Depends(tenant_session),
) -> Principal:
    claims = _claims(credentials, settings)
    if claims.tenant_id != tenant.tenant_id:
        raise ApplicationError(
            "TENANT_TOKEN_MISMATCH", "The access token is invalid.", status_code=403
        )
    user = await session.get(User, claims.user_id)
    membership = await session.scalar(
        select(TenantMembership).where(
            TenantMembership.tenant_id == tenant.tenant_id,
            TenantMembership.user_id == claims.user_id,
        )
    )
    if user is None or not user.is_active or (membership is None and not user.is_platform_admin):
        raise ApplicationError("ACCESS_DENIED", "Access is denied.", status_code=403)
    return Principal(
        user_id=user.id,
        tenant_id=tenant.tenant_id,
        role=TenantRole(membership.role) if membership else None,
        is_platform_admin=user.is_platform_admin,
    )


async def platform_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    settings: Settings = Depends(_settings),
) -> Principal:
    claims = _claims(credentials, settings)
    if not claims.is_platform_admin or claims.tenant_id is not None:
        raise ApplicationError("ACCESS_DENIED", "Platform access is denied.", status_code=403)
    database = get_database(request)
    async with database.global_session() as session:
        user = await session.get(User, claims.user_id)
        if user is None or not user.is_active or not user.is_platform_admin:
            raise ApplicationError("ACCESS_DENIED", "Platform access is denied.", status_code=403)
    return Principal(user.id, None, None, True)


PermissionDependency = Callable[..., Coroutine[Any, Any, Principal]]


def require_permission(permission: Permission) -> PermissionDependency:
    async def dependency(principal: Principal = Depends(tenant_principal)) -> Principal:
        if principal.is_platform_admin:
            return principal
        if principal.role is None or not role_has_permission(principal.role, permission):
            raise ApplicationError("PERMISSION_DENIED", "Permission is denied.", status_code=403)
        return principal

    return dependency
