from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1]))

from utils import load_json, save_json


DEFAULT_TRIPLES_PATH = Path("outputs/triples.json")
DEFAULT_GRAPH_PATH = Path("outputs/graph_nodes_edges.json")
DEFAULT_ALIAS_PATH = Path("outputs/entity_aliases.json")

PERSON_PREDICATES = {"WORKS_FOR", "CEO_OF", "REPORTS_TO"}
COMPANY_SUFFIXES = (" ltd", " limited", " corporation", " corp", " sa", " llc", " plc", " pcc")
JURISDICTION_HINTS = ("england", "wales", "luxembourg", "delaware", "guernsey", "ireland", "united states")


def normalize_entity_name(name: str) -> str:
    normalized = name.lower().strip()
    normalized = normalized.replace("&", " and ")
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def infer_entity_type(name: str, relationship_role: str, predicate: str) -> str:
    lowered = name.lower()
    if predicate in PERSON_PREDICATES and relationship_role == "subject":
        return "PERSON"
    if predicate == "INCORPORATED_IN" and relationship_role == "object":
        return "JURISDICTION"
    if any(hint in lowered for hint in JURISDICTION_HINTS) and relationship_role == "object":
        return "JURISDICTION"
    if "nominees" in lowered or "vehicles" in lowered or "structures" in lowered:
        return "SHELL_COMPANY"
    if "holding" in lowered or "group" in lowered:
        return "HOLDING_COMPANY"
    if lowered.endswith(COMPANY_SUFFIXES):
        return "COMPANY"
    return "ENTITY"


def build_nodes_and_relationships(triples: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    nodes_by_key: dict[str, dict[str, Any]] = {}
    relationships_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    aliases: dict[str, str] = {}

    for triple in triples:
        subject_key = normalize_entity_name(triple["subject"])
        object_key = normalize_entity_name(triple["object"])

        aliases.setdefault(subject_key, triple["subject"])
        aliases.setdefault(object_key, triple["object"])

        subject_node = nodes_by_key.setdefault(
            subject_key,
            {
                "canonical_name": subject_key,
                "display_name": triple["subject"],
                "entity_type": infer_entity_type(triple["subject"], "subject", triple["predicate"]),
                "aliases": [],
                "source_pages": [],
            },
        )
        object_node = nodes_by_key.setdefault(
            object_key,
            {
                "canonical_name": object_key,
                "display_name": triple["object"],
                "entity_type": infer_entity_type(triple["object"], "object", triple["predicate"]),
                "aliases": [],
                "source_pages": [],
            },
        )

        update_node(subject_node, triple["subject"], triple["source_page"])
        update_node(object_node, triple["object"], triple["source_page"])

        rel_key = (subject_key, triple["predicate"], object_key)
        relationship = relationships_by_key.setdefault(
            rel_key,
            {
                "subject_canonical_name": subject_key,
                "subject_display_name": subject_node["display_name"],
                "predicate": triple["predicate"],
                "object_canonical_name": object_key,
                "object_display_name": object_node["display_name"],
                "source_pages": [],
            },
        )
        if triple["source_page"] not in relationship["source_pages"]:
            relationship["source_pages"].append(triple["source_page"])

    nodes = sorted(nodes_by_key.values(), key=lambda node: node["display_name"])
    relationships = sorted(
        relationships_by_key.values(),
        key=lambda rel: (rel["subject_display_name"], rel["predicate"], rel["object_display_name"]),
    )
    for node in nodes:
        node["source_pages"].sort()
        node["aliases"].sort()
    for relationship in relationships:
        relationship["source_pages"].sort()
    return nodes, relationships, aliases


def update_node(node: dict[str, Any], alias: str, source_page: int) -> None:
    if alias not in node["aliases"]:
        node["aliases"].append(alias)
    if source_page not in node["source_pages"]:
        node["source_pages"].append(source_page)


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize Phase 2 triples into Neo4j-ready graph payloads.")
    parser.add_argument("--triples-path", default=str(DEFAULT_TRIPLES_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_GRAPH_PATH))
    parser.add_argument("--alias-path", default=str(DEFAULT_ALIAS_PATH))
    args = parser.parse_args()

    triple_payload = load_json(Path(args.triples_path))
    triples = triple_payload["triples"]
    nodes, relationships, aliases = build_nodes_and_relationships(triples)

    graph_payload = {
        "source_file": triple_payload["source_file"],
        "model": triple_payload["model"],
        "prompt_version": triple_payload["prompt_version"],
        "node_count": len(nodes),
        "relationship_count": len(relationships),
        "nodes": nodes,
        "relationships": relationships,
    }

    save_json(Path(args.output_path), graph_payload)
    save_json(Path(args.alias_path), aliases)
    print(
        f"Saved {graph_payload['node_count']} nodes and "
        f"{graph_payload['relationship_count']} relationships to {args.output_path}"
    )


if __name__ == "__main__":
    main()
