"""Weather agent implementation."""

from app.models import AssistantRequest, AssistantResponse, UserTokenData
from app.tools.weather_tool import get_weather_summary


async def handle_weather(
    request: AssistantRequest,
    current_user: UserTokenData,
) -> AssistantResponse:
    """Return a simple weather response."""
    summary = await get_weather_summary(request.message)
    return AssistantResponse(
        agent="weather",
        content=f"{current_user.username}, {summary}",
        style_applied=request.style,
    )
