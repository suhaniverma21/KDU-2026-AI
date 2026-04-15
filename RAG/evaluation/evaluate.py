"""Evaluation helpers for retrieval and generation quality."""

from __future__ import annotations

import argparse
import asyncio
import copy
import os
from pathlib import Path

import google.generativeai as genai
from langchain_core.outputs import Generation, LLMResult
from pipeline.generator import GeneratorError, generate_answer
from pipeline.hybrid_search import HybridSearchError, hybrid_search
from pipeline.reranker import RerankerError, rerank_results
from ragas.embeddings import GoogleEmbeddings
from ragas.llms.base import BaseRagasLLM
from utils.helpers import get_google_ai_studio_settings, load_env_file, project_root, read_json_file, stable_text_hash, write_json_file


class EvaluationError(Exception):
    """Raised when evaluation inputs or dependencies are invalid."""


load_env_file()


class GeminiRagasLLM(BaseRagasLLM):
    """Minimal Gemini-backed RAGAS LLM wrapper."""

    def __init__(self, model_name: str, api_key: str):
        super().__init__()
        genai.configure(api_key=api_key)
        self.model_name = model_name
        self.client = genai.GenerativeModel(model_name)

    def generate_text(
        self,
        prompt,
        n: int = 1,
        temperature: float = 0.01,
        stop=None,
        callbacks=None,
    ) -> LLMResult:
        text = prompt.to_string() if hasattr(prompt, "to_string") else str(prompt)
        generations = []
        for _ in range(n):
            response = self.client.generate_content(
                text,
                generation_config={"temperature": temperature},
            )
            output_text = getattr(response, "text", "") or ""
            generations.append(
                [
                    Generation(
                        text=output_text,
                        generation_info={"finish_reason": "STOP"},
                    )
                ]
            )
        return LLMResult(generations=generations)

    async def agenerate_text(
        self,
        prompt,
        n: int = 1,
        temperature: float = 0.01,
        stop=None,
        callbacks=None,
    ) -> LLMResult:
        return await asyncio.to_thread(
            self.generate_text,
            prompt,
            n,
            temperature,
            stop,
            callbacks,
        )

    def is_finished(self, response: LLMResult) -> bool:
        return True


def run_evaluation(source_id: str) -> dict:
    """Load a saved test set, run the RAG pipeline, compute metrics, and save results."""
    testset_payload = load_testset(source_id)
    rows = run_pipeline_over_testset(testset_payload)
    metrics_summary = compute_ragas_metrics(rows)
    output_path = save_evaluation_results(source_id=source_id, testset_payload=testset_payload, rows=rows, metrics_summary=metrics_summary)
    weakest_metric = identify_weakest_metric(metrics_summary)

    summary = {
        "source_id": source_id,
        "testset_items": len(rows),
        "metrics": metrics_summary,
        "weakest_metric": weakest_metric,
        "output_path": str(output_path),
    }
    print(build_console_summary(summary))
    return summary


def load_testset(source_id: str) -> dict:
    """Load the generated test set JSON for a given source."""
    testset_path = project_root() / "evaluation" / "outputs" / f"testset_{stable_text_hash(source_id)}.json"
    if not testset_path.exists():
        raise EvaluationError(f"Test set not found for source_id={source_id}. Generate it first.")
    payload = read_json_file(testset_path)
    if not payload.get("items"):
        raise EvaluationError(f"Test set for source_id={source_id} contains no items.")
    return payload


def run_pipeline_over_testset(testset_payload: dict) -> list[dict]:
    """Run retrieval and generation for each synthetic evaluation question."""
    source_id = testset_payload["source_id"]
    rows: list[dict] = []

    for item in testset_payload["items"]:
        question = item["question"]
        try:
            fused_results = hybrid_search(query=question, source_id=source_id, top_k=20)
            reranked_results = rerank_results(query=question, candidates=fused_results, top_k=5)
            generation_result = generate_answer(query=question, context_chunks=reranked_results)
        except (HybridSearchError, RerankerError, GeneratorError, ValueError) as exc:
            raise EvaluationError(f"Evaluation failed for question {item['qa_id']}: {exc}") from exc

        rows.append(
            {
                "qa_id": item["qa_id"],
                "question": question,
                "ground_truth": item["answer"],
                "generated_answer": generation_result["final_answer"],
                "contexts": [chunk.get("enriched_text", "") for chunk in generation_result["supporting_chunks"]],
                "reference_chunk_id": item["chunk_id"],
                "retrieved_chunk_ids": [chunk.get("chunk_id") for chunk in generation_result["supporting_chunks"]],
                "supporting_chunks": generation_result["supporting_chunks"],
                "debug": generation_result["debug"],
            }
        )

    return rows


def compute_ragas_metrics(rows: list[dict]) -> dict:
    """Compute available RAGAS metrics for the evaluation rows."""
    try:
        from datasets import Dataset
        from ragas import evaluate
    except ImportError as exc:
        raise EvaluationError(
            "RAGAS evaluation requires the 'ragas' and 'datasets' packages to be installed."
        ) from exc

    metric_map = _load_available_metric_map()
    requested_metrics = [
        ("context_recall", "retrieval"),
        ("context_precision", "reranking"),
        ("faithfulness", "generation"),
        ("answer_relevancy", "generation_or_prompting"),
    ]

    available_metric_names = [name for name, _stage in requested_metrics if name in metric_map]
    if not available_metric_names:
        raise EvaluationError("No requested RAGAS metrics were available in the installed version.")

    dataset = Dataset.from_list(
        [
            {
                "question": row["question"],
                "answer": row["generated_answer"],
                "ground_truth": row["ground_truth"],
                "contexts": row["contexts"],
            }
            for row in rows
        ]
    )

    settings = get_google_ai_studio_settings(
        model_env_name="GENERATION_MODEL",
        default_model="gemini-2.5-flash-lite",
    )
    llm = GeminiRagasLLM(
        model_name=settings["model"],
        api_key=settings["api_key"],
    )
    embeddings = GoogleEmbeddings(model="gemini-embedding-001")
    metrics = [
        _build_metric(metric_name=name, metric=metric_map[name], llm=llm, embeddings=embeddings)
        for name in available_metric_names
    ]

    try:
        ragas_result = evaluate(dataset=dataset, metrics=metrics, llm=llm, embeddings=embeddings)
    except TypeError:
        ragas_result = evaluate(dataset, metrics=metrics, llm=llm, embeddings=embeddings)

    ragas_result_dict = ragas_result.to_pandas().mean(numeric_only=True).to_dict()

    summary: dict[str, dict] = {}
    for metric_name, stage_hint in requested_metrics:
        if metric_name in ragas_result_dict:
            summary[metric_name] = {
                "score": float(ragas_result_dict[metric_name]),
                "likely_stage": stage_hint,
            }
    return summary


def save_evaluation_results(source_id: str, testset_payload: dict, rows: list[dict], metrics_summary: dict) -> Path:
    """Save detailed evaluation outputs to disk."""
    output_dir = project_root() / "evaluation" / "outputs"
    output_path = output_dir / f"evaluation_{stable_text_hash(source_id)}.json"
    payload = {
        "source_id": source_id,
        "testset_count": len(testset_payload["items"]),
        "evaluated_count": len(rows),
        "metrics": metrics_summary,
        "rows": rows,
    }
    write_json_file(output_path, payload)
    return output_path


def identify_weakest_metric(metrics_summary: dict) -> dict | None:
    """Return the lowest-scoring metric and its likely pipeline stage."""
    if not metrics_summary:
        return None
    metric_name = min(metrics_summary, key=lambda name: metrics_summary[name]["score"])
    return {
        "name": metric_name,
        "score": metrics_summary[metric_name]["score"],
        "likely_stage": metrics_summary[metric_name]["likely_stage"],
    }


def build_console_summary(summary: dict) -> str:
    """Build a concise printable summary for CLI use."""
    weakest = summary.get("weakest_metric")
    weakest_line = "Weakest metric: unavailable"
    if weakest:
        weakest_line = (
            f"Weakest metric: {weakest['name']}={weakest['score']:.4f} "
            f"(likely stage: {weakest['likely_stage']})"
        )

    metric_lines = [
        f"- {name}: {payload['score']:.4f} (likely stage: {payload['likely_stage']})"
        for name, payload in summary.get("metrics", {}).items()
    ]
    joined_metrics = "\n".join(metric_lines) if metric_lines else "- No metrics available"

    return (
        f"Evaluation complete for source_id={summary['source_id']}\n"
        f"Items evaluated: {summary['testset_items']}\n"
        f"{weakest_line}\n"
        f"Metrics:\n{joined_metrics}\n"
        f"Saved to: {summary['output_path']}"
    )


def _load_available_metric_map() -> dict:
    """Load supported RAGAS metrics from the installed package version."""
    try:
        import ragas.metrics as ragas_metrics
    except ImportError as exc:
        raise EvaluationError("The installed environment does not include ragas.metrics.") from exc

    metric_names = [
        "context_recall",
        "context_precision",
        "faithfulness",
        "answer_relevancy",
    ]
    metric_map: dict[str, object] = {}
    for metric_name in metric_names:
        if not hasattr(ragas_metrics, metric_name):
            continue

        metric_map[metric_name] = getattr(ragas_metrics, metric_name)

    return metric_map


def _build_metric(metric_name: str, metric, llm, embeddings):
    """Return a metric instance compatible with the installed RAGAS version."""
    if hasattr(metric, "single_turn_ascore") or hasattr(metric, "_required_columns"):
        metric_instance = copy.deepcopy(metric)
        if hasattr(metric_instance, "llm"):
            metric_instance.llm = llm
        if metric_name == "answer_relevancy" and hasattr(metric_instance, "embeddings"):
            metric_instance.embeddings = embeddings
        return metric_instance

    if isinstance(metric, type):
        if metric_name == "answer_relevancy":
            return metric(llm=llm, embeddings=embeddings)
        return metric(llm=llm)

    return metric


def _parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Run RAGAS evaluation for one indexed source.")
    parser.add_argument("--source-id", required=True, help="The source_id used during indexing.")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run_evaluation(source_id=args.source_id)
