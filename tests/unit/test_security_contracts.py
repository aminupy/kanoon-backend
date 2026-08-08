from __future__ import annotations

import jwt
import pytest
from pydantic import ValidationError

from app.auth.models import TenantRole
from app.auth.permissions import Permission, role_has_permission
from app.auth.security import verify_state
from app.core.config import Settings
from app.registrations.schemas import RegistrationPatch
from app.registrations.validation import (
    normalize_iranian_mobile,
    validate_iranian_national_code,
)


def test_mobile_normalization_collapses_equivalent_inputs() -> None:
    values = ["09123456789", "+989123456789", "00989123456789"]
    assert {normalize_iranian_mobile(value) for value in values} == {"+989123456789"}


def test_national_code_checksum() -> None:
    assert validate_iranian_national_code("1234567891") == "1234567891"
    with pytest.raises(ValueError):
        validate_iranian_national_code("1234567890")


def test_registration_client_cannot_supply_payment_state() -> None:
    with pytest.raises(ValidationError):
        RegistrationPatch.model_validate({"payment_status": "SUCCESSFUL"})


def test_role_permission_boundaries() -> None:
    assert all(
        role_has_permission(TenantRole.TENANT_ADMIN, permission) for permission in Permission
    )
    assert role_has_permission(TenantRole.CONTENT_EDITOR, Permission.CONTENT_WRITE)
    assert not role_has_permission(TenantRole.CONTENT_EDITOR, Permission.CONTENT_PUBLISH)
    assert not role_has_permission(TenantRole.CONTENT_EDITOR, Permission.REGISTRATION_READ)
    assert role_has_permission(TenantRole.REGISTRATION_MANAGER, Permission.REGISTRATION_EXPORT)
    assert not role_has_permission(TenantRole.REGISTRATION_MANAGER, Permission.FINANCE_READ)
    assert role_has_permission(TenantRole.FINANCE_VIEWER, Permission.FINANCE_READ)
    assert not role_has_permission(TenantRole.FINANCE_VIEWER, Permission.REGISTRATION_WRITE)


def test_production_rejects_mock_providers() -> None:
    with pytest.raises(ValidationError, match="mock OTP/payment providers"):
        Settings(environment="production", debug=False, signing_key="x" * 64)


def test_invalid_payment_callback_state_is_rejected() -> None:
    with pytest.raises(jwt.InvalidTokenError):
        verify_state(Settings(environment="testing"), "payment_callback", "not-a-signed-token")
