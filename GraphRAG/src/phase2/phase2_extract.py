from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from openai import OpenAI

sys.path.append(str(Path(__file__).resolve().parents[1]))

from utils import ensure_directories, get_llm_client_config, get_pdf_path, load_pdf_pages, save_json


PHASE2_PROMPT_VERSION = "phase2_v1"
DEFAULT_OUTPUT_PATH = Path("outputs/triples.json")
DEFAULT_PAGES_PATH = Path("outputs/pages.json")
RAW_DIR = Path("outputs/phase2_raw")


def build_extraction_messages(page_number: int, page_text: str) -> list[dict[str, str]]:
    system_prompt = (
        "You extract knowledge-graph triples from corporate documents. "
        "Return JSON only. Do not include markdown fences or commentary. "
        "Extract only relationships that are explicitly stated in the text. "
        "Use this schema exactly: "
        '[{"subject":"...", "predicate":"...", "object":"...", "source_page":1}] '
        "Predicates must be uppercase with underscores and chosen from: "
        "WORKS_FOR, CEO_OF, OWNED_BY, PARENT_OF, REPORTS_TO, INCORPORATED_IN, TRADING_NAME_OF. "
        "Deduplicate repeated facts within the same page."
    )
    user_prompt = (
        f"Source page: {page_number}\n"
        "Extract all explicit corporate ownership, executive, reporting, jurisdiction, and naming relationships.\n"
        "Return only a JSON array.\n\n"
        f"Page text:\n{page_text}"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def build_repair_messages(raw_text: str, page_number: int) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Repair malformed JSON. Return only a valid JSON array of triple objects using the "
                'schema [{"subject":"...", "predicate":"...", "object":"...", "source_page":1}].'
            ),
        },
        {
            "role": "user",
            "content": f"Page number: {page_number}\nRepair this into valid JSON only:\n{raw_text}",
        },
    ]


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


def extract_json_array(text: str) -> Any:
    cleaned = strip_code_fences(text)
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON array found in model output")
    return json.loads(cleaned[start : end + 1])


def validate_triple(item: dict[str, Any], page_number: int) -> dict[str, Any]:
    required = {"subject", "predicate", "object"}
    missing = required - set(item)
    if missing:
        raise ValueError(f"Missing keys in triple: {sorted(missing)}")

    triple = {
        "subject": str(item["subject"]).strip(),
        "predicate": str(item["predicate"]).strip().upper(),
        "object": str(item["object"]).strip(),
        "source_page": int(item.get("source_page", page_number)),
    }

    if not triple["subject"] or not triple["object"] or not triple["predicate"]:
        raise ValueError("Triple fields must be non-empty")

    return triple


def get_phase2_llm_config() -> dict:
    config = get_llm_client_config()
    if not config:
        raise EnvironmentError(
            "Missing OPENROUTER_API_KEY or OPENAI_API_KEY. Phase 2 extraction requires an LLM."
        )

    config = dict(config)
    config["model"] = os.getenv("PHASE2_LLM_MODEL", "meta-llama/llama-3.1-8b-instruct")
    return config


def call_llm(messages: list[dict[str, str]], model: str, api_key: str, base_url: str) -> str:
    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=messages,
    )
    return response.choices[0].message.content or ""


def extract_page_triples(
    page: dict[str, Any],
    model: str,
    api_key: str,
    base_url: str,
    allow_repair: bool,
) -> dict[str, Any]:
    page_number = page["page_number"]
    raw_text = call_llm(
        messages=build_extraction_messages(page_number=page_number, page_text=page["text"]),
        model=model,
        api_key=api_key,
        base_url=base_url,
    )

    try:
        parsed = extract_json_array(raw_text)
    except Exception:
        if not allow_repair:
            raise
        repaired_text = call_llm(
            messages=build_repair_messages(raw_text=raw_text, page_number=page_number),
            model=model,
            api_key=api_key,
            base_url=base_url,
        )
        raw_text = repaired_text
        parsed = extract_json_array(repaired_text)

    triples = [validate_triple(item, page_number=page_number) for item in parsed]
    return {
        "page_number": page_number,
        "raw_output": raw_text,
        "triples": deduplicate_triples(triples),
    }


def deduplicate_triples(triples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, int]] = set()
    unique: list[dict[str, Any]] = []

    for triple in triples:
        key = (
            triple["subject"],
            triple["predicate"],
            triple["object"],
            triple["source_page"],
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(triple)

    return unique


def write_raw_output(page_number: int, payload: dict[str, Any]) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / f"page_{page_number:02d}.json"
    save_json(raw_path, payload)


def build_payload(source_file: str, pages: list[dict[str, Any]], page_results: list[dict[str, Any]], model: str) -> dict:
    triples = [triple for result in page_results for triple in result["triples"]]
    return {
        "source_file": source_file,
        "prompt_version": PHASE2_PROMPT_VERSION,
        "model": model,
        "page_count": len(pages),
        "triple_count": len(triples),
        "pages": [{"page_number": page["page_number"], "char_count": page["char_count"]} for page in pages],
        "triples": triples,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Phase 2 knowledge-graph triples from the PDF.")
    parser.add_argument("--pdf-path", default=None)
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--pages-output-path", default=str(DEFAULT_PAGES_PATH))
    parser.add_argument("--allow-repair", action="store_true")
    args = parser.parse_args()

    ensure_directories()
    pdf_path = get_pdf_path(args.pdf_path)
    pages = load_pdf_pages(pdf_path)
    save_json(Path(args.pages_output_path), {"source_file": pdf_path.name, "pages": pages})

    config = get_phase2_llm_config()
    page_results = []

    for page in pages:
        result = extract_page_triples(
            page=page,
            model=config["model"],
            api_key=config["api_key"],
            base_url=config["base_url"],
            allow_repair=args.allow_repair,
        )
        page_results.append(result)
        write_raw_output(page["page_number"], result)

    payload = build_payload(
        source_file=pdf_path.name,
        pages=pages,
        page_results=page_results,
        model=config["model"],
    )
    save_json(Path(args.output_path), payload)
    print(f"Saved {payload['triple_count']} triples to {args.output_path}")


if __name__ == "__main__":
    main()
