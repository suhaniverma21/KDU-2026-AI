"""Simple hybrid router for choosing which chat flow to run.

We first use deterministic rules for obvious requests because they are fast
and easy to understand. If the request is not obvious, we use a small LLM
classifier to choose between a limited set of route values.
"""

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from app.agents.model_selector import get_model_for_task
from app.config import settings
from app.utils.safety import contains_strong_jailbreak_attempt


WEATHER_KEYWORDS = ["weather", "temperature", "rain", "hot", "cold", "forecast"]
MEMORY_KEYWORDS = ["earlier", "before", "last time", "previous", "you said", "we discussed"]
ALLOWED_ROUTES = {"chat", "weather", "image", "memory_chat"}


def _looks_like_weather_request(message: str) -> bool:
    lowered = message.lower()
    return any(keyword in lowered for keyword in WEATHER_KEYWORDS)


def _looks_like_memory_request(message: str) -> bool:
    lowered = message.lower()
    return any(keyword in lowered for keyword in MEMORY_KEYWORDS)


def classify_route_with_model(message: str) -> str:
    """Use a small constrained classifier when the route is not obvious."""
    if not settings.google_api_key:
        return "chat"

    try:
        model_name = get_model_for_task("chat")
        # Gemini Flash is enough for this small classification task.
        model = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=settings.google_api_key,
            temperature=0,
        )
        response = model.invoke(
            [
                SystemMessage(
                    content=(
                        "Classify the user request as exactly one of these labels: "
                        "chat, weather, image, memory_chat. "
                        "Return only one label and nothing else."
                    )
                ),
                HumanMessage(content=message),
            ]
        )
        route = (response.content or "").strip().lower()
    except Exception:
        return "chat"

    if route not in ALLOWED_ROUTES:
        return "chat"
    return route


def route_request(
    message: str,
    image_url: str | None = None,
    image_path: str | None = None,
) -> str:
    """Return the route name for the incoming request.

    Hybrid routing is better than keyword-only routing because it keeps
    obvious cases simple, while still handling less obvious messages.
    """
    # If the request is a clear jailbreak attempt, never route it toward
    # tools or special handling paths. The main endpoint will block it.
    if contains_strong_jailbreak_attempt(message):
        return "chat"

    if image_url or image_path:
        return "image"

    if _looks_like_weather_request(message):
        return "weather"

    if _looks_like_memory_request(message):
        return "memory_chat"

    return classify_route_with_model(message)
