"""FastAPI application entry point."""

from __future__ import annotations

import logging
from datetime import datetime, UTC

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exceptions import AppException, default_message_for_status, status_code_to_error_code
from app.core.logging import configure_logging
from app.middleware.logging_middleware import LoggingMiddleware
from app.middleware.request_context import get_request_id
from app.schemas.error import ErrorResponse

settings = get_settings()
configure_logging()
error_logger = logging.getLogger("app.error")

app = FastAPI(title="FastAPI Production Template")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LoggingMiddleware)

app.include_router(api_router, prefix="/api/v1")


def build_error_response(
    *,
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Create a standardized JSON error response."""
    request_id = getattr(request.state, "request_id", None) or get_request_id()
    payload = ErrorResponse(
        success=False,
        error={
            "code": code,
            "message": message,
            "details": details or {},
            "timestamp": datetime.now(UTC),
            "path": request.url.path,
            "request_id": request_id,
        },
    )
    response = JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json"),
        headers=headers,
    )
    if request_id:
        response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handle custom business exceptions with the standardized error schema."""
    return build_error_response(
        request=request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Transform request validation errors into the standardized error schema."""
    return build_error_response(
        request=request,
        status_code=422,
        code="VALIDATION_ERROR",
        message="Request validation failed",
        details={"validation_errors": jsonable_encoder(exc.errors())},
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    """Transform framework and HTTP exceptions into the standardized error schema."""
    detail = exc.detail
    if isinstance(detail, str):
        message = detail
        details: dict[str, object] = {}
    else:
        message = default_message_for_status(exc.status_code)
        details = {"detail": detail}

    headers: dict[str, str] | None = None
    if exc.status_code == 401:
        headers = {"WWW-Authenticate": "Bearer"}

    return build_error_response(
        request=request,
        status_code=exc.status_code,
        code=status_code_to_error_code(exc.status_code),
        message=message,
        details=details,
        headers=headers,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected errors without exposing internal details to clients."""
    error_logger.exception(
        "Unhandled application exception",
        extra={
            "request_id": getattr(request.state, "request_id", None) or get_request_id(),
            "method": request.method,
            "path": request.url.path,
            "status_code": 500,
        },
    )
    return build_error_response(
        request=request,
        status_code=500,
        code="INTERNAL_SERVER_ERROR",
        message="An unexpected error occurred",
    )


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Return a simple health status for uptime checks."""
    return {"status": "ok"}
