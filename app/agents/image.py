"""Simple image analysis helper for multimodal chat."""

import base64
import json
import mimetypes
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from app.agents.model_selector import get_model_for_task
from app.config import settings
from app.middleware.style_middleware import get_final_tone_instruction
from app.utils.safety import validate_text_output


def _image_path_to_data_url(image_path: str) -> str:
    """Convert a local image file into a data URL.

    Gemini can read an image from a normal URL or from a base64 data URL.
    This helper makes local files easier to send.
    """
    path = Path(image_path)
    if not path.exists() or not path.is_file():
        raise ValueError("Image path is invalid")

    mime_type, _ = mimetypes.guess_type(path.name)
    if not mime_type or not mime_type.startswith("image/"):
        raise ValueError("Image path must point to an image file")

    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def _clean_json_text(text: str) -> str:
    """Remove optional markdown fences before JSON parsing."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.replace("json", "", 1).strip()
    return cleaned


def analyze_image(
    message: str,
    image_url: str | None = None,
    image_path: str | None = None,
    style: str = "casual",
) -> tuple[dict, str]:
    """Analyze one image with a vision-capable Gemini model.

    This is part of the multimodal assistant idea: the same chat endpoint can
    now accept text plus an image. We use a vision-capable model because a
    normal text-only model cannot inspect image pixels.
    """
    if not settings.google_api_key:
        raise ValueError("GOOGLE_API_KEY is missing")

    if not image_url and not image_path:
        raise ValueError("Image input is required")

    final_image_url = image_url
    if image_path:
        final_image_url = _image_path_to_data_url(image_path)

    _final_style, style_instruction = get_final_tone_instruction(style, message)

    messages = [
        SystemMessage(
            content=(
                "You analyze images for a beginner-friendly assistant. "
                "Return only valid JSON with keys: description, objects, "
                f"scene_type, safety_rating. {style_instruction}"
            )
        ),
        HumanMessage(
            content=[
                {
                    "type": "text",
                    "text": (
                        f"User request: {message}\n"
                        "Describe the image simply and list a few main objects."
                    ),
                },
                {
                    "type": "image_url",
                    "image_url": {"url": final_image_url},
                },
            ]
        ),
    ]

    try:
        # Image tasks use the vision model because the model needs to inspect
        # image content, not only text.
        model_name = get_model_for_task("image")
        # Gemini Pro is used here because image tasks need a stronger
        # multimodal model than normal text chat.
        model = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=settings.google_api_key,
            temperature=0,
        )
        response = model.invoke(messages)
        data = json.loads(_clean_json_text(response.content))
    except json.JSONDecodeError as exc:
        raise ValueError("Image analysis returned an invalid response") from exc
    except Exception as exc:
        raise ValueError(f"Could not analyze image: {exc}") from exc

    result = {
        "description": str(data.get("description", "")),
        "objects": [str(item) for item in data.get("objects", [])],
        "scene_type": str(data.get("scene_type", "unknown")),
        "safety_rating": str(data.get("safety_rating", "unknown")),
    }
    output_error = validate_text_output(result["description"])
    if output_error:
        raise ValueError(output_error)

    return (result, model_name)
