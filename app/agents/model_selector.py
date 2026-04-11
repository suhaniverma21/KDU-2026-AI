"""Simple helper for choosing which model to use for each task.

Model switching is useful because not every task needs the same model.
Regular chat and summaries can use a smaller, cheaper text model, while
image analysis should use a model that is better suited for vision work.
"""

from app.config import settings


def get_model_for_task(task_type: str) -> str:
    """Return the model name for the given task type."""
    # Gemini model switching keeps the same architecture:
    # - flash-lite for normal text tasks
    # - flash for stronger multimodal work
    if task_type == "image":
        return settings.vision_model

    # Chat and summaries both use the normal text model.
    if task_type == "summary":
        return settings.text_model

    return settings.text_model
