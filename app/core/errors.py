from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette import status
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger(__name__)

RequestHandler = Callable[[Request], Awaitable[JSONResponse]]


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str
    details: dict[str, Any] = Field(default_factory=dict)


class ApplicationError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class ErrorBoundaryMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Any]]
    ) -> Any:
        try:
            return await call_next(request)
        except ApplicationError as exc:
            body = ErrorBody(
                code=exc.code,
                message=exc.message,
                request_id=_request_id(request),
                details=exc.details,
            )
            return JSONResponse(status_code=exc.status_code, content=body.model_dump())
        except Exception as exc:
            logger.error(
                "unhandled_request_error",
                request_id=_request_id(request),
                exception_type=type(exc).__name__,
            )
            body = ErrorBody(
                code="INTERNAL_SERVER_ERROR",
                message="An unexpected error occurred.",
                request_id=_request_id(request),
            )
            return JSONResponse(status_code=500, content=body.model_dump())


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "unknown"))


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApplicationError)
    async def application_error_handler(request: Request, exc: ApplicationError) -> JSONResponse:
        body = ErrorBody(
            code=exc.code,
            message=exc.message,
            request_id=_request_id(request),
            details=exc.details,
        )
        return JSONResponse(status_code=exc.status_code, content=body.model_dump())

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = {
            "errors": [
                {"type": error["type"], "loc": error["loc"], "msg": error["msg"]}
                for error in exc.errors()
            ]
        }
        body = ErrorBody(
            code="REQUEST_VALIDATION_FAILED",
            message="The request did not pass validation.",
            request_id=_request_id(request),
            details=details,
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, content=body.model_dump()
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        # The exception is logged by request middleware without serializing request bodies.
        body = ErrorBody(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected error occurred.",
            request_id=_request_id(request),
        )
        return JSONResponse(status_code=500, content=body.model_dump())
