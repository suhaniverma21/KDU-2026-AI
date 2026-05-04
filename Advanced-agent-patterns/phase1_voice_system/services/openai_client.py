"""Creates provider clients for OpenAI speech, transcription, and model calls."""

from openai import OpenAI

from config.settings import get_settings


def get_openai_client() -> OpenAI:
    """Create an OpenAI client configured from environment-backed settings."""
    settings = get_settings()
    return OpenAI(api_key=settings.openai_api_key)
