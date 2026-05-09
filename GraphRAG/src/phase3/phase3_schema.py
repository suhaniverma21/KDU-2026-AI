from __future__ import annotations

SCHEMA_VERSION = "phase3_v1"

ALLOWED_NODE_LABELS = ["Entity"]
ALLOWED_NODE_PROPERTIES = [
    "canonical_name",
    "name",
    "type",
    "aliases",
    "source_pages",
]
ALLOWED_RELATIONSHIP_TYPES = [
    "WORKS_FOR",
    "CEO_OF",
    "OWNED_BY",
    "PARENT_OF",
    "REPORTS_TO",
    "INCORPORATED_IN",
    "TRADING_NAME_OF",
]

READ_ONLY_KEYWORDS = ["MATCH", "WHERE", "RETURN", "WITH", "ORDER BY", "LIMIT", "OPTIONAL MATCH"]
FORBIDDEN_CYPHER_KEYWORDS = [
    "CREATE",
    "MERGE",
    "DELETE",
    "DETACH",
    "SET",
    "REMOVE",
    "DROP",
    "CALL",
    "LOAD CSV",
    "FOREACH",
]


def get_schema_prompt() -> str:
    return (
        "Graph schema:\n"
        "- Node labels: Entity\n"
        "- Node properties: canonical_name, name, type, aliases, source_pages\n"
        "- Relationship types: WORKS_FOR, CEO_OF, OWNED_BY, PARENT_OF, REPORTS_TO, INCORPORATED_IN, TRADING_NAME_OF\n"
        "- Return a variable named p for the path when possible.\n"
        "- Use only read-only Cypher."
    )
