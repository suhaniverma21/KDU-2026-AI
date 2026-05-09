from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1]))

from phase3_schema import FORBIDDEN_CYPHER_KEYWORDS
from utils import load_project_env

try:
    from neo4j import GraphDatabase
except ImportError:  # pragma: no cover
    GraphDatabase = None


def require_driver():
    if GraphDatabase is None:
        raise ImportError(
            "The neo4j package is not installed. Install it with `pip install neo4j` before running Phase 3."
        )
    return GraphDatabase


def get_connection_settings() -> dict[str, str]:
    load_project_env()

    uri = os.getenv("NEO4J_URI", "").strip()
    username = os.getenv("NEO4J_USERNAME", "").strip()
    password = os.getenv("NEO4J_PASSWORD", "").strip()

    if not uri or not username or not password:
        raise EnvironmentError("Missing NEO4J_URI, NEO4J_USERNAME, or NEO4J_PASSWORD environment variables.")

    return {"uri": uri, "username": username, "password": password}


def validate_query_is_read_only(cypher: str) -> None:
    upper = cypher.upper()
    for keyword in FORBIDDEN_CYPHER_KEYWORDS:
        if keyword in upper:
            raise ValueError(f"Forbidden Cypher keyword found: {keyword}")


def serialize_path(path) -> dict[str, Any]:
    nodes = []
    relationships = []

    for node in path.nodes:
        nodes.append(
            {
                "id": node.element_id,
                "labels": list(node.labels),
                "properties": dict(node),
            }
        )

    for relationship in path.relationships:
        rel_nodes = list(relationship.nodes)
        relationships.append(
            {
                "id": relationship.element_id,
                "type": relationship.type,
                "start_node_id": rel_nodes[0].element_id,
                "end_node_id": rel_nodes[1].element_id,
                "properties": dict(relationship),
            }
        )

    return {"nodes": nodes, "relationships": relationships}


def execute_cypher(cypher: str) -> dict[str, Any]:
    validate_query_is_read_only(cypher)
    driver_cls = require_driver()
    settings = get_connection_settings()
    driver = driver_cls.driver(settings["uri"], auth=(settings["username"], settings["password"]))

    try:
        with driver.session() as session:
            result = session.run(cypher)
            record = result.single()
            if record is None:
                return {"success": True, "path_found": False, "path": None, "error": None}

            path_value = None
            if "p" in record.keys():
                path_value = record["p"]
            elif len(record.keys()) == 1:
                path_value = record[0]
            else:
                raise ValueError("Cypher query did not return a path variable named `p`.")

            if path_value is None:
                return {"success": True, "path_found": False, "path": None, "error": None}

            return {
                "success": True,
                "path_found": True,
                "path": serialize_path(path_value),
                "error": None,
            }
    except Exception as exc:
        return {"success": False, "path_found": False, "path": None, "error": str(exc)}
    finally:
        driver.close()
