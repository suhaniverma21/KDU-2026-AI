"""Memory management helpers."""


def build_memory_snippet(user_id: str, query: str) -> str:
    """Create a placeholder memory snippet."""
    return f"recent context for {user_id} related to '{query}'"
