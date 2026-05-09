from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from utils import load_json


DEFAULT_GRAPH_PATH = Path("outputs/graph_nodes_edges.json")
DEFAULT_ALIAS_PATH = Path("outputs/entity_aliases.json")
DEFAULT_REPORT_PATH = Path("outputs/phase2_report.md")


def build_report(graph_payload: dict, alias_payload: dict) -> str:
    nodes = graph_payload["nodes"]
    relationships = graph_payload["relationships"]
    duplicate_alias_groups = [canonical for canonical, display in alias_payload.items() if canonical != display.lower()]

    lines = [
        "# Phase 2 Report",
        "",
        "## Setup",
        "",
        f"- Source file: `{graph_payload['source_file']}`",
        f"- Extraction model: `{graph_payload['model']}`",
        "- Graph store target: `Neo4j AuraDB`",
        f"- Node count: `{graph_payload['node_count']}`",
        f"- Relationship count: `{graph_payload['relationship_count']}`",
        "",
        "## Entity Resolution",
        "",
        "Entity names were normalized with lowercase comparison keys, punctuation stripping, and whitespace cleanup before insertion.",
        "",
        "Nodes were merged by canonical name, while preserving display names, aliases, and source pages for traceability.",
        "",
        "## Duplicate Handling",
        "",
        "The graph payload is designed to prevent duplicate nodes by using `canonical_name` as the merge key in Neo4j.",
        "",
        f"- Alias entries recorded: `{len(alias_payload)}`",
        f"- Potential alias review cases: `{len(duplicate_alias_groups)}`",
        "",
        "## Improvements",
        "",
        "- Add a reviewed alias dictionary for borderline company-name variants.",
        "- Add confidence scoring for entity merges instead of only deterministic normalization.",
        "- Add post-extraction validation rules for suspicious ownership gaps or repeated entity variants.",
        "",
        "## Sample Relationships",
        "",
    ]

    for relationship in relationships[:10]:
        lines.append(
            f"- `{relationship['subject_display_name']} -[{relationship['predicate']}]-> {relationship['object_display_name']}` "
            f"(pages: {relationship['source_pages']})"
        )

    lines.extend(
        [
            "",
            "## Sample Nodes",
            "",
        ]
    )

    for node in nodes[:10]:
        lines.append(
            f"- `{node['display_name']}` type=`{node['entity_type']}` pages=`{node['source_pages']}` aliases=`{node['aliases']}`"
        )

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a Phase 2 Markdown report from graph outputs.")
    parser.add_argument("--graph-path", default=str(DEFAULT_GRAPH_PATH))
    parser.add_argument("--alias-path", default=str(DEFAULT_ALIAS_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_REPORT_PATH))
    args = parser.parse_args()

    graph_payload = load_json(Path(args.graph_path))
    alias_payload = load_json(Path(args.alias_path))
    report = build_report(graph_payload, alias_payload)
    Path(args.output_path).write_text(report, encoding="utf-8")
    print(f"Saved Phase 2 report to {args.output_path}")


if __name__ == "__main__":
    main()
