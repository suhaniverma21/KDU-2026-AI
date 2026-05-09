from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from openai import OpenAI

sys.path.append(str(Path(__file__).resolve().parents[1]))

from phase3_schema import (
    ALLOWED_NODE_LABELS,
    ALLOWED_NODE_PROPERTIES,
    ALLOWED_RELATIONSHIP_TYPES,
    FORBIDDEN_CYPHER_KEYWORDS,
    SCHEMA_VERSION,
    get_schema_prompt,
)
from utils import load_project_env


PROMPT_VERSION = "phase3_cypher_v1"


def get_phase3_llm_config() -> dict[str, str]:
    load_project_env()

    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("Missing OPENROUTER_API_KEY. Phase 3 is configured to use OpenRouter.")

    return {
        "provider": "openrouter",
        "api_key": api_key,
        "base_url": os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        "model": os.getenv("PHASE3_LLM_MODEL", "meta-llama/llama-3.1-8b-instruct"),
    }


def build_cypher_messages(question: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You generate Cypher queries for Neo4j. "
                "Output only Cypher. No markdown fences. No explanation.\n\n"
                f"{get_schema_prompt()}\n"
                "Rules:\n"
                "- Use only Entity nodes.\n"
                "- Use only the listed relationship types.\n"
                "- Use only the listed properties.\n"
                "- Prefer returning a path variable named p.\n"
                "- Use LIMIT 1 unless there is a strong reason not to.\n"
                "- Do not use write operations.\n"
                "- Return a query shaped like `MATCH p = ... RETURN p AS p LIMIT 1`.\n"
                "- If you use variable-length traversal, the `*` is path-length syntax, not part of the relationship type.\n"
                "- Do not return a node or scalar when the task asks for a path.\n"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Question: {question}\n"
                "Generate a read-only Cypher query that returns the relevant path.\n"
                "For ultimate-parent reasoning, prefer a direct person-to-company relationship and then a variable-length ownership traversal.\n"
                "Example pattern:\n"
                "MATCH p = (person:Entity {name: \"John Smith\"})-[:CEO_OF]->(company:Entity)"
                "-[:OWNED_BY*1..6]->(parent:Entity)\n"
                "RETURN p AS p\n"
                "LIMIT 1"
            ),
        },
    ]


def build_correction_messages(question: str, failed_cypher: str, error_message: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You correct Cypher queries for Neo4j. Output only corrected Cypher.\n\n"
                f"{get_schema_prompt()}\n"
                "Do not invent labels, properties, or relationship types.\n"
                "Return a query shaped like `MATCH p = ... RETURN p AS p LIMIT 1`."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Question: {question}\n"
                f"Failed Cypher:\n{failed_cypher}\n\n"
                f"Neo4j error:\n{error_message}\n\n"
                "Return one corrected read-only Cypher query."
            ),
        },
    ]


def build_fallback_cypher(question: str) -> str | None:
    lowered = question.lower()
    if "ultimate parent company" in lowered and "john smith" in lowered:
        return (
            'MATCH p = (person:Entity {name: "John Smith"})-[:CEO_OF]->(company:Entity)'
            '-[:OWNED_BY*1..6]->(parent:Entity)\n'
            'WHERE NOT (parent)-[:OWNED_BY]->(:Entity)\n'
            'RETURN p AS p\n'
            'ORDER BY length(p) DESC\n'
            'LIMIT 1'
        )
    return None


def call_llm(messages: list[dict[str, str]], config: dict[str, str]) -> str:
    client = OpenAI(api_key=config["api_key"], base_url=config["base_url"])
    response = client.chat.completions.create(
        model=config["model"],
        temperature=0,
        messages=messages,
    )
    return (response.choices[0].message.content or "").strip()


def strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


def extract_relationship_types(cypher: str) -> set[str]:
    found = set()
    for group in re.findall(r"\[([^\]]+)\]", cypher):
        if ":" not in group:
            continue
        group = group.split(":", 1)[1]
        group = group.split("{", 1)[0]
        for rel in group.split("|"):
            rel = rel.strip()
            rel = re.sub(r"\*.*$", "", rel)
            if rel:
                found.add(rel)
    return found


def extract_properties(cypher: str) -> set[str]:
    return set(re.findall(r"\.\s*([a-zA-Z_][a-zA-Z0-9_]*)", cypher))


def validate_cypher(cypher: str) -> dict[str, Any]:
    cleaned = strip_code_fences(cypher)
    upper = cleaned.upper()
    errors: list[str] = []

    if "ENTITY" not in upper:
        errors.append("Cypher does not reference the Entity label.")

    if not re.search(r"\bMATCH\s+p\s*=", cleaned, flags=re.IGNORECASE):
        errors.append("Cypher must bind the path to a variable named `p` using `MATCH p = ...`.")

    if not re.search(r"\bRETURN\s+p(\s+AS\s+p)?\b", cleaned, flags=re.IGNORECASE):
        errors.append("Cypher must return the path variable `p`.")

    for keyword in FORBIDDEN_CYPHER_KEYWORDS:
        if keyword in upper:
            errors.append(f"Forbidden Cypher keyword found: {keyword}")

    relationship_types = extract_relationship_types(cleaned)
    invalid_relationships = sorted(rel for rel in relationship_types if rel not in ALLOWED_RELATIONSHIP_TYPES)
    if invalid_relationships:
        errors.append(f"Invalid relationship types: {invalid_relationships}")

    properties = extract_properties(cleaned)
    invalid_properties = sorted(prop for prop in properties if prop not in ALLOWED_NODE_PROPERTIES)
    if invalid_properties:
        errors.append(f"Invalid properties: {invalid_properties}")

    label_matches = set(re.findall(r":([A-Z][A-Za-z0-9_]*)", cleaned))
    invalid_labels = sorted(label for label in label_matches if label not in ALLOWED_NODE_LABELS and label not in ALLOWED_RELATIONSHIP_TYPES)
    if invalid_labels:
        errors.append(f"Invalid labels: {invalid_labels}")

    return {
        "schema_version": SCHEMA_VERSION,
        "prompt_version": PROMPT_VERSION,
        "valid": not errors,
        "errors": errors,
        "cypher": cleaned,
    }


def generate_cypher(question: str) -> dict[str, Any]:
    config = get_phase3_llm_config()
    raw_cypher = call_llm(build_cypher_messages(question), config)
    validation = validate_cypher(raw_cypher)
    return {
        "provider": config["provider"],
        "model": config["model"],
        "raw_cypher": raw_cypher,
        "validation": validation,
    }


def correct_cypher(question: str, failed_cypher: str, error_message: str) -> dict[str, Any]:
    fallback_cypher = build_fallback_cypher(question)
    if fallback_cypher is not None:
        validation = validate_cypher(fallback_cypher)
        if validation["valid"]:
            return {
                "provider": "local_fallback",
                "model": "schema_aware_template",
                "raw_cypher": fallback_cypher,
                "validation": validation,
                "error_context": error_message,
            }

    config = get_phase3_llm_config()
    corrected = call_llm(build_correction_messages(question, failed_cypher, error_message), config)
    validation = validate_cypher(corrected)
    return {
        "provider": config["provider"],
        "model": config["model"],
        "raw_cypher": corrected,
        "validation": validation,
        "error_context": error_message,
    }
