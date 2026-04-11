"""Chat agent implementation."""

from app.models import AssistantRequest, AssistantResponse, UserTokenData
from app.tools.memory_tool import search_memory


async def handle_chat(
    request: AssistantRequest,
    current_user: UserTokenData,
) -> AssistantResponse:
    """Return a simple chat response using memory context."""
    memory_hint = search_memory(current_user.username, request.message)
    content = f"Chat response for {current_user.username}: {request.message}"
    if memory_hint:
        content = f"{content} | Memory: {memory_hint}"

    return AssistantResponse(
        agent="chat",
        content=content,
        style_applied=request.style,
    )
