"""Database memory search helper."""

from app.utils.memory import build_memory_snippet


def search_memory(user_id: str, query: str) -> str:
    """Return a simple memory snippet for the current request."""
    return build_memory_snippet(user_id, query)
