from __future__ import annotations

from typing import Any

from app.main import app


def operations_by_id(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        operation["operationId"]: operation
        for path_item in schema["paths"].values()
        for method, operation in path_item.items()
        if method in {"get", "post", "put", "patch", "delete"}
    }


def test_openapi_reuses_structured_application_error_responses() -> None:
    schema = app.openapi()
    assert "ErrorBody" in schema["components"]["schemas"]
    responses = schema["components"]["responses"]
    assert {f"Error{status}" for status in (400, 401, 403, 404, 409, 413, 422, 429, 503)} <= set(
        responses
    )
    for response in responses.values():
        body = response["content"]["application/json"]["schema"]
        assert body == {"$ref": "#/components/schemas/ErrorBody"}


def test_openapi_documents_applicable_runtime_error_statuses() -> None:
    operations = operations_by_id(app.openapi())

    admin_protected = {
        operation_id
        for operation_id in operations
        if "_api_v1_admin_" in operation_id and not operation_id.startswith("tenant_")
    }
    assert admin_protected
    for operation_id in admin_protected:
        assert {"401", "403", "404"} <= set(operations[operation_id]["responses"])

    expected = {
        "tenant_login_api_v1_admin_auth_login_post": {"401", "404", "422", "429"},
        "tenant_refresh_api_v1_admin_auth_refresh_post": {"401", "404", "422"},
        "patch_registration_api_v1_public_registrations__registration_id__patch": {
            "400",
            "401",
            "404",
            "409",
            "422",
        },
        "complete_upload_api_v1_admin_media_uploads__media_id__complete_post": {
            "401",
            "403",
            "404",
            "409",
            "422",
        },
        (
            "complete_profile_image_upload_api_v1_public_registrations__registration_id__"
            "profile_image__media_id__complete_post"
        ): {
            "401",
            "404",
            "409",
            "422",
        },
        "initiate_upload_api_v1_admin_media_uploads_post": {"401", "403", "404", "413", "422"},
        (
            "initiate_profile_image_upload_api_v1_public_registrations__registration_id__"
            "profile_image_upload_post"
        ): {
            "401",
            "404",
            "413",
            "422",
        },
        "create_contact_request_api_v1_public_contact_requests_post": {"404", "422", "429"},
        "record_build_result_api_v1_internal_site_builds__request_id__result_post": {
            "401",
            "404",
            "409",
            "422",
        },
        "ready_health_ready_get": {"503"},
    }
    for operation_id, statuses in expected.items():
        assert statuses <= set(operations[operation_id]["responses"]), operation_id

    assert (
        "409"
        not in operations["archive_resource_api_v1_admin__resource___entity_id__delete"][
            "responses"
        ]
    )
    assert "409" not in operations["list_posts_api_v1_admin_posts_get"]["responses"]
    assert (
        "429"
        not in operations[
            "verify_otp_api_v1_public_registrations__registration_id__otp_verify_post"
        ]["responses"]
    )
    assert (
        "400"
        not in operations[
            "rotate_draft_token_api_v1_public_registrations__registration_id__token_rotate_post"
        ]["responses"]
    )

    for operation_id in (
        "get_blog_post_api_v1_public_blog__slug__get",
        "news_detail_api_v1_public_news__slug__get",
        "announcement_detail_api_v1_public_announcements__slug__get",
        "gallery_detail_api_v1_public_gallery__slug__get",
        "download_media_api_v1_public_media__media_id__get",
    ):
        assert "404" in operations[operation_id]["responses"]


def test_registration_csv_is_documented_as_attachment_text_csv_only() -> None:
    operation = operations_by_id(app.openapi())[
        "export_registrations_api_v1_admin_registrations_export_csv_get"
    ]
    success = operation["responses"]["200"]
    assert set(success["content"]) == {"text/csv"}
    assert success["content"]["text/csv"]["schema"] == {"type": "string", "format": "binary"}
    assert success["headers"]["Content-Disposition"]["schema"]["type"] == "string"
