"""Application-specific exception types and error helpers."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any


class AppException(Exception):
    """Base application exception with a stable error code and HTTP status."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the exception metadata used by the global handlers."""
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


class ConflictError(AppException):
    """Conflict error for duplicate or incompatible resources."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "RESOURCE_CONFLICT",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Create a 409 conflict exception."""
        super().__init__(status_code=409, code=code, message=message, details=details)


class AuthenticationError(AppException):
    """Authentication failure error."""

    def __init__(
        self,
        message: str = "Could not validate credentials",
        *,
        code: str = "AUTHENTICATION_FAILED",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Create a 401 authentication exception."""
        super().__init__(status_code=401, code=code, message=message, details=details)


class AuthorizationError(AppException):
    """Authorization failure error."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "FORBIDDEN",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Create a 403 authorization exception."""
        super().__init__(status_code=403, code=code, message=message, details=details)


class ResourceNotFoundError(AppException):
    """Resource-not-found exception."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "RESOURCE_NOT_FOUND",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Create a 404 not found exception."""
        super().__init__(status_code=404, code=code, message=message, details=details)


def status_code_to_error_code(status_code: int) -> str:
    """Map an HTTP status code to a stable default error code."""
    mapping = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "RESOURCE_NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "RESOURCE_CONFLICT",
        422: "VALIDATION_ERROR",
        500: "INTERNAL_SERVER_ERROR",
    }
    return mapping.get(status_code, f"HTTP_{status_code}")


def default_message_for_status(status_code: int) -> str:
    """Return a safe default message for a status code."""
    if status_code == 500:
        return "An unexpected error occurred"
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "Request failed"
