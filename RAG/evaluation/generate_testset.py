"""Synthetic evaluation dataset generation."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from pipeline.bm25_index import BM25IndexError, load_index_artifacts
from utils.helpers import (
    call_google_ai_studio_generate_content,
    get_google_ai_studio_settings,
    load_env_file,
    project_root,
    stable_text_hash,
    write_json_file,
)


DEFAULT_PROVIDER = "google_ai_studio"
DEFAULT_MODEL = "gemini-2.5-flash-lite"
DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_NUM_QUESTIONS = 15
MAX_NUM_QUESTIONS = 20

load_env_file()


class TestsetGenerationError(Exception):
    """Raised when synthetic test-set generation fails."""


def generate_testset(source_id: str, num_questions: int = DEFAULT_NUM_QUESTIONS) -> list[dict]:
    """Generate and save a synthetic QA test set from persisted indexed chunks."""
    if num_questions <= 0 or num_questions > MAX_NUM_QUESTIONS:
        raise TestsetGenerationError(f"num_questions must be between 1 and {MAX_NUM_QUESTIONS}.")

    try:
        artifact = load_index_artifacts(source_id=source_id)
    except BM25IndexError as exc:
        raise TestsetGenerationError(str(exc)) from exc

    records = artifact["records"]
    if not records:
        raise TestsetGenerationError("No indexed chunks were available for test-set generation.")

    selected_records = records[: min(num_questions, len(records))]
    qa_pairs: list[dict] = []

    for index, record in enumerate(selected_records, start=1):
        prompt = build_testset_prompt(record=record, question_number=index)
        qa_payload = call_testset_generation_api(prompt)
        qa_pairs.append(build_testset_entry(source_id=source_id, record=record, qa_payload=qa_payload, question_number=index))

    save_testset(source_id=source_id, qa_pairs=qa_pairs, requested_count=num_questions)
    return qa_pairs


def build_testset_prompt(record: dict, question_number: int) -> str:
    """Build a strict chunk-grounded QA generation prompt."""
    enriched_text = record.get("enriched_text", "")
    raw_text = record.get("raw_text", "")
    return (
        "Create exactly one question-answer pair from the chunk below.\n"
        "The question must be answerable from this chunk alone.\n"
        "Prefer a specific factual question over a vague summary question.\n"
        "Do not use outside knowledge. Do not invent facts.\n"
        "The answer must be concise and fully supported by the chunk.\n"
        "Return valid JSON only with keys: question, answer.\n\n"
        f"Question number: {question_number}\n"
        f"Chunk ID: {record.get('chunk_id')}\n"
        f"Enriched chunk:\n{enriched_text}\n\n"
        f"Raw chunk:\n{raw_text}\n"
    )


def call_testset_generation_api(prompt: str) -> dict:
    """Call the Google AI Studio Gemini API for QA generation."""
    settings = get_google_ai_studio_settings(
        model_env_name="GENERATION_MODEL",
        default_model=DEFAULT_MODEL,
        default_provider=DEFAULT_PROVIDER,
        default_base_url=DEFAULT_BASE_URL,
    )
    provider = settings["provider"]
    if provider != "google_ai_studio":
        raise TestsetGenerationError(f"Unsupported test-set provider: {provider}")

    try:
        content = call_google_ai_studio_generate_content(
            prompt=prompt,
            system_prompt="You create strict chunk-grounded evaluation question-answer pairs in JSON.",
            model=settings["model"],
            base_url=settings["base_url"],
            api_key=settings["api_key"],
            timeout=60,
            temperature=0,
        )
    except RuntimeError as exc:
        raise TestsetGenerationError("Failed to call the test-set generation API.") from exc

    try:
        parsed = parse_json_response(content)
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raw_preview = str(content)[:1000]
        raise TestsetGenerationError(
            f"Test-set generation API returned invalid JSON. Raw response preview: {raw_preview}"
        ) from exc

    if not parsed.get("question") or not parsed.get("answer"):
        raise TestsetGenerationError("Generated QA payload must contain question and answer.")
    return parsed


def parse_json_response(content: str) -> dict:
    """Parse JSON from a model response, tolerating markdown code fences and wrapper text."""
    text = str(content).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced_match:
        return json.loads(fenced_match.group(1))

    object_match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if object_match:
        return json.loads(object_match.group(0))

    raise json.JSONDecodeError("No JSON object found in response.", text, 0)


def build_testset_entry(source_id: str, record: dict, qa_payload: dict, question_number: int) -> dict:
    """Build one saved test-set entry with traceable metadata."""
    question = str(qa_payload["question"]).strip()
    answer = str(qa_payload["answer"]).strip()
    entry_id = stable_text_hash(f"{source_id}::{record['chunk_id']}::{question}", prefix="qa_")

    return {
        "qa_id": entry_id,
        "question_number": question_number,
        "source_id": source_id,
        "chunk_id": record["chunk_id"],
        "question": question,
        "answer": answer,
        "source_trace": {
            "chunk_id": record["chunk_id"],
            "source_id": source_id,
            "metadata": record.get("metadata", {}),
        },
        "chunk_snapshot": {
            "enriched_text": record.get("enriched_text", ""),
            "raw_text": record.get("raw_text", ""),
        },
    }


def save_testset(source_id: str, qa_pairs: list[dict], requested_count: int) -> Path:
    """Save the generated test set as JSON."""
    output_dir = project_root() / "evaluation" / "outputs"
    output_path = output_dir / f"testset_{stable_text_hash(source_id)}.json"
    payload = {
        "source_id": source_id,
        "requested_count": requested_count,
        "generated_count": len(qa_pairs),
        "items": qa_pairs,
    }
    write_json_file(output_path, payload)
    return output_path


def _parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Generate a synthetic QA test set for one indexed source.")
    parser.add_argument("--source-id", required=True, help="The source_id used during indexing.")
    parser.add_argument("--num-questions", type=int, default=DEFAULT_NUM_QUESTIONS, help="Number of QA pairs to generate.")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    generated = generate_testset(source_id=args.source_id, num_questions=args.num_questions)
    print(f"Generated {len(generated)} QA pairs for source_id={args.source_id}")
