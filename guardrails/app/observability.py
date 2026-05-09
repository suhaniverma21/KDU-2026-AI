import os


def is_langsmith_enabled() -> bool:
    tracing = os.getenv("LANGSMITH_TRACING", "").lower()
    api_key = os.getenv("LANGSMITH_API_KEY")
    return tracing == "true" and bool(api_key)


def get_langsmith_project() -> str | None:
    return os.getenv("LANGSMITH_PROJECT")
