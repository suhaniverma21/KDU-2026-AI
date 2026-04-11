"""Pydantic models for authentication, profile, and chat APIs."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


ALLOWED_STYLES = {"expert", "child", "casual"}


class UserSignupRequest(BaseModel):
    """Data needed to create a new account."""

    email: str
    password: str


class UserLoginRequest(BaseModel):
    """Data needed to log in."""

    email: str
    password: str


class TokenResponse(BaseModel):
    """JWT token returned after login."""

    access_token: str
    token_type: str = "bearer"


class MessageResponse(BaseModel):
    """Simple success message used by small endpoints."""

    message: str


class HealthResponse(BaseModel):
    """Health check response."""

    status: str


class DatabaseStatusResponse(BaseModel):
    """Database check response."""

    database: str


class TokenPayload(BaseModel):
    """Basic data stored inside the JWT."""

    sub: str


class UserProfileResponse(BaseModel):
    """Profile data returned to the client."""

    email: str
    location: str = ""
    style: str = "casual"


class ProfileResponse(UserProfileResponse):
    """Alias-style profile response for clearer API naming."""


class UserProfileUpdateRequest(BaseModel):
    """Profile fields the client can update."""

    location: str = Field(default="", description="Simple location text like Bengaluru")
    style: str = Field(default="casual", description="Learning style for future assistant responses")

    @field_validator("style")
    @classmethod
    def validate_style(cls, value: str) -> str:
        """Allow only the small set of styles for now."""
        if value not in ALLOWED_STYLES:
            raise ValueError("style must be one of: expert, child, casual")
        return value


class ErrorResponse(BaseModel):
    """Consistent error shape used across the API."""

    error: str
    details: Any | None = None


class ChatRequest(BaseModel):
    """Chat input from the authenticated user."""

    message: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    image_url: str | None = None
    image_path: str | None = None


class ChatResponse(BaseModel):
    """Chat reply returned by the API."""

    session_id: str
    reply: str
    style: str
    route: str
    model_used: str


class WeatherResponse(BaseModel):
    """Simple weather data returned by the weather tool."""

    temperature: float
    summary: str
    location: str
    route: str
    model_used: str | None = None


class ImageAnalysisResponse(BaseModel):
    """Simple structured response for image analysis."""

    description: str
    objects: list[str]
    scene_type: str
    safety_rating: str
    route: str
    model_used: str


class ConversationMessageResponse(BaseModel):
    """One saved chat message from the conversation history."""

    role: str
    content: str
    created_at: datetime


class ConversationHistoryResponse(BaseModel):
    """Recent messages for one chat session."""

    session_id: str
    messages: list[ConversationMessageResponse]


class HistoryResponse(ConversationHistoryResponse):
    """Alias-style history response for clearer API naming."""
