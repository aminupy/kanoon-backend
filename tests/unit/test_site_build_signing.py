from __future__ import annotations

import time

import pytest

from app.core.errors import ApplicationError
from app.site_builds.signing import sign_message, verify_message


def test_hmac_build_signature_binds_method_path_body_and_time() -> None:
    secret = "test-build-secret-that-is-long-enough"
    timestamp = int(time.time())
    body = b'{"result":"SUCCESSFUL"}'
    signature = sign_message(secret, timestamp, "POST", "/callback", body)
    verify_message(
        secret=secret,
        timestamp_value=str(timestamp),
        signature=signature,
        method="POST",
        path="/callback",
        body=body,
        max_age_seconds=60,
    )
    with pytest.raises(ApplicationError):
        verify_message(
            secret=secret,
            timestamp_value=str(timestamp),
            signature=signature,
            method="POST",
            path="/callback",
            body=b'{"result":"FAILED"}',
            max_age_seconds=60,
        )


def test_stale_build_signature_is_rejected() -> None:
    timestamp = int(time.time()) - 120
    secret = "test-build-secret-that-is-long-enough"
    with pytest.raises(ApplicationError) as error:
        verify_message(
            secret=secret,
            timestamp_value=str(timestamp),
            signature=sign_message(secret, timestamp, "POST", "/callback", b"{}"),
            method="POST",
            path="/callback",
            body=b"{}",
            max_age_seconds=60,
        )
    assert error.value.code == "BUILD_SIGNATURE_EXPIRED"
