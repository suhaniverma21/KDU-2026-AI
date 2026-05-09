from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx

try:
    from neo4j import GraphDatabase
except ImportError:  # pragma: no cover
    GraphDatabase = None

sys.path.append(str(Path(__file__).resolve().parents[1]))

from utils import load_project_env


DEFAULT_IMAGE_PATH = Path("outputs/phase2_graph.png")

NODE_COLORS = {
    "PERSON": "#d97706",
    "COMPANY": "#2563eb",
    "SHELL_COMPANY": "#7c3aed",
    "HOLDING_COMPANY": "#059669",
    "JURISDICTION": "#64748b",
    "ENTITY": "#475569",
}


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


def fetch_graph_records() -> tuple[list[dict], list[dict]]:
    driver_cls = require_driver()
    settings = get_connection_settings()
    driver = driver_cls.driver(settings["uri"], auth=(settings["username"], settings["password"]))
    try:
        with driver.session() as session:
            node_result = session.run(
                "MATCH (e:Entity) RETURN e.canonical_name AS canonical_name, e.name AS name, e.type AS type"
            )
            rel_result = session.run(
                """
                MATCH (s:Entity)-[r]->(o:Entity)
                RETURN s.canonical_name AS subject_canonical_name,
                       s.name AS subject_name,
                       type(r) AS predicate,
                       o.canonical_name AS object_canonical_name,
                       o.name AS object_name
                """
            )
            nodes = [record.data() for record in node_result]
            relationships = [record.data() for record in rel_result]
    finally:
        driver.close()
    return nodes, relationships


def build_graph(nodes: list[dict], relationships: list[dict]) -> nx.DiGraph:
    graph = nx.DiGraph()

    for node in nodes:
        graph.add_node(
            node["canonical_name"],
            label=node["name"],
            entity_type=node.get("type") or "ENTITY",
        )

    for relationship in relationships:
        graph.add_edge(
            relationship["subject_canonical_name"],
            relationship["object_canonical_name"],
            label=relationship["predicate"],
        )

    return graph


def render_graph(graph: nx.DiGraph, output_path: Path) -> None:
    plt.figure(figsize=(16, 10))
    positions = nx.spring_layout(graph, seed=42, k=1.2)
    node_colors = [
        NODE_COLORS.get(graph.nodes[node].get("entity_type", "ENTITY"), NODE_COLORS["ENTITY"])
        for node in graph.nodes
    ]
    labels = {node: graph.nodes[node]["label"] for node in graph.nodes}
    edge_labels = {(u, v): attrs["label"] for u, v, attrs in graph.edges(data=True)}

    nx.draw_networkx_nodes(graph, positions, node_color=node_colors, node_size=1800, alpha=0.95)
    nx.draw_networkx_edges(graph, positions, arrows=True, arrowstyle="-|>", arrowsize=18, width=1.6)
    nx.draw_networkx_labels(graph, positions, labels=labels, font_size=8)
    nx.draw_networkx_edge_labels(graph, positions, edge_labels=edge_labels, font_size=7)

    plt.axis("off")
    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a Phase 2 graph visualization from Neo4j data.")
    parser.add_argument("--output-path", default=str(DEFAULT_IMAGE_PATH))
    args = parser.parse_args()

    nodes, relationships = fetch_graph_records()
    graph = build_graph(nodes, relationships)
    render_graph(graph, Path(args.output_path))
    print(f"Saved graph visualization to {args.output_path}")


if __name__ == "__main__":
    main()
