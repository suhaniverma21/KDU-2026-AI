from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1]))

from utils import load_json, load_project_env

try:
    from neo4j import GraphDatabase
except ImportError:  # pragma: no cover
    GraphDatabase = None


DEFAULT_GRAPH_PATH = Path("outputs/graph_nodes_edges.json")
VALID_REL_PATTERN = re.compile(r"^[A-Z_]+$")


def require_driver():
    if GraphDatabase is None:
        raise ImportError(
            "The neo4j package is not installed. Install it with `pip install neo4j` before running Phase 2."
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


def create_constraints(session) -> None:
    session.run(
        "CREATE CONSTRAINT entity_canonical_name IF NOT EXISTS "
        "FOR (e:Entity) REQUIRE e.canonical_name IS UNIQUE"
    )


def merge_node(session, node: dict[str, Any]) -> None:
    session.run(
        """
        MERGE (e:Entity {canonical_name: $canonical_name})
        ON CREATE SET
          e.name = $display_name,
          e.type = $entity_type,
          e.aliases = $aliases,
          e.source_pages = $source_pages
        ON MATCH SET
          e.name = coalesce(e.name, $display_name),
          e.type = coalesce(e.type, $entity_type),
          e.aliases = $aliases,
          e.source_pages = $source_pages
        """,
        canonical_name=node["canonical_name"],
        display_name=node["display_name"],
        entity_type=node["entity_type"],
        aliases=node["aliases"],
        source_pages=node["source_pages"],
    )


def merge_relationship(session, relationship: dict[str, Any]) -> None:
    predicate = relationship["predicate"]
    if not VALID_REL_PATTERN.match(predicate):
        raise ValueError(f"Unsafe relationship type: {predicate}")

    query = f"""
    MATCH (s:Entity {{canonical_name: $subject_canonical_name}})
    MATCH (o:Entity {{canonical_name: $object_canonical_name}})
    MERGE (s)-[r:{predicate}]->(o)
    ON CREATE SET r.source_pages = $source_pages
    ON MATCH SET r.source_pages = $source_pages
    """
    session.run(
        query,
        subject_canonical_name=relationship["subject_canonical_name"],
        object_canonical_name=relationship["object_canonical_name"],
        source_pages=relationship["source_pages"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Load the Phase 2 graph payload into Neo4j AuraDB.")
    parser.add_argument("--graph-path", default=str(DEFAULT_GRAPH_PATH))
    args = parser.parse_args()

    driver_cls = require_driver()
    settings = get_connection_settings()
    payload = load_json(Path(args.graph_path))

    driver = driver_cls.driver(settings["uri"], auth=(settings["username"], settings["password"]))
    try:
        with driver.session() as session:
            create_constraints(session)
            for node in payload["nodes"]:
                merge_node(session, node)
            for relationship in payload["relationships"]:
                merge_relationship(session, relationship)
    finally:
        driver.close()

    print(
        f"Loaded {payload['node_count']} nodes and "
        f"{payload['relationship_count']} relationships into Neo4j"
    )


if __name__ == "__main__":
    main()
