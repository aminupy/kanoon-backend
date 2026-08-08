from __future__ import annotations

from enum import StrEnum

from app.auth.models import TenantRole


class Permission(StrEnum):
    CONTENT_READ = "content:read"
    CONTENT_WRITE = "content:write"
    CONTENT_PUBLISH = "content:publish"
    SITE_BUILD_READ = "site_build:read"
    SITE_BUILD_REQUEST = "site_build:request"
    PROFILE_WRITE = "profile:write"
    REGISTRATION_READ = "registration:read"
    REGISTRATION_WRITE = "registration:write"
    REGISTRATION_EXPORT = "registration:export"
    CONTACT_READ = "contact:read"
    FINANCE_READ = "finance:read"
    MEMBERSHIP_WRITE = "membership:write"
    FEATURE_WRITE = "feature:write"


ROLE_PERMISSIONS: dict[TenantRole, frozenset[Permission]] = {
    TenantRole.TENANT_ADMIN: frozenset(Permission),
    TenantRole.CONTENT_EDITOR: frozenset(
        {Permission.CONTENT_READ, Permission.CONTENT_WRITE, Permission.PROFILE_WRITE}
    ),
    TenantRole.REGISTRATION_MANAGER: frozenset(
        {
            Permission.REGISTRATION_READ,
            Permission.REGISTRATION_WRITE,
            Permission.REGISTRATION_EXPORT,
            Permission.CONTACT_READ,
        }
    ),
    TenantRole.FINANCE_VIEWER: frozenset({Permission.REGISTRATION_READ, Permission.FINANCE_READ}),
}


def role_has_permission(role: TenantRole, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS[role]
