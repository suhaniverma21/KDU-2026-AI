"""Middleware for structured request logging."""

from __future__ import annotations

import logging
import time
from uuid import UUID, uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.middleware.request_context import reset_request_id, set_request_id

logger = logging.getLogger("app.request")


class LoggingMiddleware(BaseHTTPMiddleware):
    """Log request metadata and attach a request id to every response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        """Log request completion details without exposing sensitive input data."""
        request_id = self._resolve_request_id(request)
        request.state.request_id = request_id
        token = set_request_id(request_id)
        start_time = time.perf_counter()
        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

            response.headers["X-Request-ID"] = request_id
            logger.info(
                "Request completed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
            return response
        finally:
            reset_request_id(token)

    @staticmethod
    def _resolve_request_id(request: Request) -> str:
        """Return a request id from the header when valid, or generate a new UUID."""
        candidate = request.headers.get("X-Request-ID")
        if candidate:
            try:
                return str(UUID(candidate))
            except ValueError:
                return str(uuid4())
        return str(uuid4())
