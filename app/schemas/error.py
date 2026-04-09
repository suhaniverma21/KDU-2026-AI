"""Pydantic schemas for standardized API error responses."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    """Structured error payload returned by the API."""

    code: str = Field(..., description="Stable machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional structured metadata about the error",
    )
    timestamp: datetime = Field(..., description="Time the error response was generated")
    path: str = Field(..., description="Request path associated with the error")
    request_id: str | None = Field(
        default=None,
        description="Correlation identifier for tracing the request",
    )


class ErrorResponse(BaseModel):
    """Envelope for every handled error response."""

    success: bool = Field(default=False, description="Always false for error responses")
    error: ErrorBody
