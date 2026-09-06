from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI

from app.core.errors import ErrorBody

ERROR_DESCRIPTIONS = {
    400: "The request conflicts with a business rule or resource state.",
    401: "Authentication is required or the supplied credential is invalid.",
    403: "The authenticated principal is not permitted to perform this operation.",
    404: "The requested tenant or resource was not found.",
    409: "The request conflicts with the current resource or integration state.",
    413: "The request declares content larger than the configured limit.",
    422: "The request did not pass structural or semantic validation.",
    429: "The request was rejected by a bounded rate limit.",
    503: "A required service dependency is unavailable.",
}

ADMIN_CONFLICT_OPERATIONS = frozenset(
    {
        "create_banner_api_v1_admin_banners_post",
        "create_blog_post_api_v1_admin_blog_post",
        "create_exam_api_v1_admin_exams_post",
        "create_gallery_api_v1_admin_gallery_post",
        "create_gallery_item_api_v1_admin_gallery__album_id__items_post",
        "create_honor_api_v1_admin_honors_post",
        "create_honor_category_api_v1_admin_honor_categories_post",
        "create_post_api_v1_admin_posts_post",
        "create_pricing_api_v1_admin_pricing_plans_post",
        "create_sample_exam_api_v1_admin_sample_exams_post",
        "create_staff_api_v1_admin_staff_post",
        "publish_blog_post_api_v1_admin_blog__post_id__publish_post",
        "update_banner_api_v1_admin_banners__entity_id__put",
        "update_blog_post_api_v1_admin_blog__post_id__patch",
        "update_exam_api_v1_admin_exams__entity_id__put",
        "update_gallery_album_api_v1_admin_gallery__entity_id__put",
        "update_honor_api_v1_admin_honors__entity_id__put",
        "update_honor_category_api_v1_admin_honor_categories__entity_id__put",
        "update_post_api_v1_admin_posts__entity_id__put",
        "update_pricing_plan_api_v1_admin_pricing_plans__entity_id__put",
        "update_sample_exam_api_v1_admin_sample_exams__entity_id__put",
        "update_staff_api_v1_admin_staff__entity_id__put",
        "complete_upload_api_v1_admin_media_uploads__media_id__complete_post",
    }
)

REGISTRATION_BUSINESS_RULE_OPERATIONS = frozenset(
    {
        "create_registration_api_v1_public_registrations_post",
        "patch_registration_api_v1_public_registrations__registration_id__patch",
        "put_contacts_api_v1_public_registrations__registration_id__contacts_put",
        "verify_otp_api_v1_public_registrations__registration_id__otp_verify_post",
        "submit_registration_api_v1_public_registrations__registration_id__submit_post",
        "initiate_payment_api_v1_public_registrations__registration_id__payment_post",
    }
)

REGISTRATION_CONFLICT_OPERATIONS = frozenset(
    {
        "patch_registration_api_v1_public_registrations__registration_id__patch",
        (
            "complete_profile_image_upload_api_v1_public_registrations__registration_id__"
            "profile_image__media_id__complete_post"
        ),
        "submit_registration_api_v1_public_registrations__registration_id__submit_post",
        "initiate_payment_api_v1_public_registrations__registration_id__payment_post",
    }
)


def _error_statuses(
    *, path: str, method: str, operation_id: str, existing_responses: dict[str, Any]
) -> set[int]:
    """Return only error statuses reachable by a route or its dependencies."""

    statuses = {422} if "422" in existing_responses else set()
    if path == "/health/ready":
        return {503}
    if path.startswith("/api/v1/admin/auth/"):
        statuses.update({401, 404})  # credential rejection and tenant resolution
        if operation_id.endswith("login_post"):
            statuses.add(429)
        return statuses
    if path.startswith("/api/v1/admin/"):
        statuses.update({401, 403, 404})
        if path.startswith("/api/v1/admin/registrations/") and method == "patch":
            statuses.add(400)
        if operation_id in ADMIN_CONFLICT_OPERATIONS:
            statuses.add(409)
        if operation_id == "initiate_upload_api_v1_admin_media_uploads_post":
            statuses.add(413)
        return statuses
    if path.startswith("/api/v1/public/registrations"):
        statuses.add(404)  # tenant, exam, registration, or draft access is deliberately opaque
        if operation_id != "create_registration_api_v1_public_registrations_post":
            statuses.add(401)
        if operation_id in REGISTRATION_BUSINESS_RULE_OPERATIONS:
            statuses.add(400)
        if operation_id in REGISTRATION_CONFLICT_OPERATIONS:
            statuses.add(409)
        if path.endswith("/profile-image/upload"):
            statuses.add(413)
        if path.endswith("/otp/send"):
            statuses.add(429)
        return statuses
    if path.startswith("/api/v1/public/payments/callback/"):
        statuses.update({401, 404})
        return statuses
    if path.startswith("/api/v1/internal/site-builds/"):
        statuses.update({401, 404, 409, 422})
        return statuses
    if path.startswith("/api/v1/public/"):
        statuses.add(404)  # all public routes pass tenant/feature resolution
        if path == "/api/v1/public/contact-requests":
            statuses.add(429)
        if path == "/api/v1/public/blog/snapshot":
            statuses.add(409)
        return statuses
    return statuses


def install_openapi_contract(application: FastAPI) -> None:
    """Install the canonical generated contract with reusable application errors."""

    original_openapi: Callable[[], dict[str, Any]] = application.openapi

    def custom_openapi() -> dict[str, Any]:
        if application.openapi_schema is not None:
            return application.openapi_schema
        schema = original_openapi()
        components = schema.setdefault("components", {})
        schemas = components.setdefault("schemas", {})
        schemas["ErrorBody"] = ErrorBody.model_json_schema(
            ref_template="#/components/schemas/{model}"
        )
        reusable_responses = components.setdefault("responses", {})
        for status_code, description in ERROR_DESCRIPTIONS.items():
            reusable_responses[f"Error{status_code}"] = {
                "description": description,
                "content": {
                    "application/json": {"schema": {"$ref": "#/components/schemas/ErrorBody"}}
                },
            }

        for path, path_item in schema.get("paths", {}).items():
            for method, operation in path_item.items():
                if method not in {"get", "post", "put", "patch", "delete"}:
                    continue
                responses = operation.setdefault("responses", {})
                statuses = _error_statuses(
                    path=path,
                    method=method,
                    operation_id=operation["operationId"],
                    existing_responses=responses,
                )
                for status_code in statuses:
                    responses[str(status_code)] = {
                        "$ref": f"#/components/responses/Error{status_code}"
                    }

                if operation["operationId"] == (
                    "export_registrations_api_v1_admin_registrations_export_csv_get"
                ):
                    responses["200"] = {
                        "description": "Registration export.",
                        "headers": {
                            "Content-Disposition": {
                                "description": "Attachment filename.",
                                "schema": {"type": "string"},
                            }
                        },
                        "content": {"text/csv": {"schema": {"type": "string", "format": "binary"}}},
                    }

        application.openapi_schema = schema
        return schema

    application.openapi = custom_openapi  # type: ignore[method-assign]
