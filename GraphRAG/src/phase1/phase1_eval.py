from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from phase1_rag import run
from utils import ATTACK_QUERY, build_ground_truth


def build_report(result: dict) -> str:
    retrieval = result["retrieval"]
    analysis = result["failure_analysis"]
    ground_truth = build_ground_truth()
    ground_truth = result["failure_analysis"]["ground_truth"]
    retrieved_pages = analysis["retrieved_pages"]
    retrieved_page_set = sorted(set(retrieved_pages))

    report_lines = [
        "# Phase 1 Report",
        "",
        "## Setup",
        "",
        f"- Document: `data/{result['source_file']}`",
        "- Chunking: fixed-size character chunking",
        "- Chunk size: `700`",
        "- Chunk overlap: `100`",
        "- Vector store: `ChromaDB`",
        "- Embedding model: `local_tfidf_baseline`",
        f"- Query: `{result['query']}`",
        f"- Top-k: `{result['top_k']}`",
        "",
        "## Retrieved Evidence",
        "",
        f"- Retrieved pages: `{retrieved_page_set}`",
        f"- Retrieved chunk count: `{len(retrieval['retrieved_chunks'])}`",
        "",
        "## Final Answer",
        "",
        result["answer"],
        "",
        "## Why Vector RAG Failed",
        "",
        "The question asks for the ultimate parent company of the organization John Smith works for. "
        "That answer requires combining multiple ownership links spread across separate pages rather than matching one locally similar passage.",
        "",
        f"The retriever ranks chunks by semantic similarity to the query. Chunks that mention `John Smith` or `{ground_truth['works_for']}` are more similar to the query than the chunk on Page 5 that names `{ground_truth['ultimate_parent_company']}` as the ultimate parent. Because of that, the distant ownership fact can be missed or ranked too low.",
        "",
        "Fixed-size chunking also breaks the ownership chain into isolated fragments. Each chunk is embedded independently, so the system retrieves separate local facts instead of a connected reasoning path from employee -> company -> intermediate holding company -> strategic umbrella -> ultimate parent.",
        "",
        "## Answers to the Required Questions",
        "",
        "### Why did the retriever fail to fetch the chunk from page 1 or the true top-level ownership evidence?",
        "",
        f"It favored chunks whose wording overlapped with the query. Employment-related chunks mention `John Smith` and `{ground_truth['works_for']}`, so they are closer in vector space than high-level ownership chunks that do not mention John Smith directly.",
        "",
        "### Why does chunking break multi-hop reasoning?",
        "",
        "Each chunk becomes its own embedding. The ownership chain is split across pages, so no single chunk contains the full reasoning path. The retriever scores chunks one by one, not relationships between chunks, which means the system can miss a necessary bridge in the chain.",
        "",
        "## Ground Truth",
        "",
        f"- John Smith works for: `{ground_truth['works_for']}`",
        f"- Ownership path: `{ ' -> '.join(ground_truth['ownership_path']) }`",
        f"- Ultimate parent company: `{ground_truth['ultimate_parent_company']}`",
        "",
        "## Retrieved Chunks",
        "",
    ]

    for chunk in retrieval["retrieved_chunks"]:
        report_lines.extend(
            [
                f"### Rank {chunk['rank']} - Page {chunk['page_number']} - {chunk['chunk_id']}",
                "",
                chunk["text"],
                "",
            ]
        )

    return "\n".join(report_lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Phase 1 attack query and generate a report.")
    parser.add_argument("--query", default=ATTACK_QUERY)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--chunks-path", default="outputs/chunks.json")
    args = parser.parse_args()

    result = run(query=args.query, top_k=args.top_k, chunks_path=args.chunks_path)
    Path("outputs/retrieval_results.json").write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )
    report = build_report(result)
    Path("outputs/phase1_report.md").write_text(report, encoding="utf-8")

    print("Saved JSON results to outputs/retrieval_results.json")
    print("Saved Markdown report to outputs/phase1_report.md")


if __name__ == "__main__":
    main()
