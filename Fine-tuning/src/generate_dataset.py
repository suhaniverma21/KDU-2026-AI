from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from random import Random
from typing import Any

from openai import OpenAI

from dsl_spec import EXAMPLES, SYSTEM_INSTRUCTIONS, build_fewshot_prompt
from env_loader import load_local_env
from validate_dsl import validate_dsl


SERVICES = [
    "billing-api",
    "inventory-api",
    "search-api",
    "checkout-worker",
    "audit-db",
    "session-gateway",
    "api-firewall",
    "user-db",
    "notification-api",
    "pricing-api",
    "report-builder",
    "auth-worker",
]

SYNTHETIC_BLUEPRINTS = [
    (
        "Deploy {service} to {env} {window_phrase}.",
        'OPS|INTENT=DEPLOY|SERVICE="{service}"|ENV="{env}"|PRIORITY={priority}|APPROVAL={approval}|NOTIFY={notify}|WINDOW="{window}"|TAGS=["release","{tag}"]',
    ),
    (
        "Scale {service} in {env} {urgency_phrase}.",
        'OPS|INTENT=SCALE|SERVICE="{service}"|ENV="{env}"|PRIORITY={priority}|APPROVAL={approval}|NOTIFY={notify}|WINDOW="{window}"|TAGS=["scaling","{tag}"]',
    ),
    (
        "Restart {service} in {env} during business hours.",
        'OPS|INTENT=RESTART|SERVICE="{service}"|ENV="{env}"|PRIORITY={priority}|APPROVAL={approval}|NOTIFY={notify}|WINDOW="BUSINESS_HOURS"|TAGS=["restart","{tag}"]',
    ),
    (
        "Back up {service} in {env} on Saturday 0200Z.",
        'OPS|INTENT=BACKUP|SERVICE="{service}"|ENV="{env}"|PRIORITY={priority}|APPROVAL={approval}|NOTIFY={notify}|WINDOW="MAINTENANCE_SAT_0200Z"|TAGS=["backup","{tag}"]',
    ),
    (
        "Patch {service} in {env} on Sunday 0100Z for a security release.",
        'OPS|INTENT=PATCH|SERVICE="{service}"|ENV="{env}"|PRIORITY={priority}|APPROVAL={approval}|NOTIFY={notify}|WINDOW="MAINTENANCE_SUN_0100Z"|TAGS=["patch","security"]',
    ),
]


def extract_usage(response: Any) -> dict[str, int | None]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {"input_tokens": None, "output_tokens": None, "total_tokens": None}
    return {
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def extract_json_array(text: str) -> list[dict[str, Any]]:
    stripped = text.strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("[")
        end = stripped.rfind("]")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("Model output did not contain a parseable JSON array.") from None
        parsed = json.loads(stripped[start : end + 1])

    if not isinstance(parsed, list):
        raise ValueError("Expected the model to return a JSON array.")
    return parsed


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")


def normalize_record(item: dict[str, Any]) -> tuple[dict[str, str] | None, dict[str, Any] | None]:
    messages = item.get("messages")
    if not isinstance(messages, list):
        return None, {"record": item, "errors": ["Missing messages list."]}

    try:
        user_message = next(message for message in messages if message.get("role") == "user")
        assistant_message = next(message for message in messages if message.get("role") == "assistant")
    except StopIteration:
        return None, {"record": item, "errors": ["Record must include user and assistant messages."]}

    request = str(user_message.get("content", "")).strip()
    dsl = str(assistant_message.get("content", "")).strip()
    result = validate_dsl(dsl)
    if not request or not result.is_valid:
        return None, {"record": item, "errors": result.errors or ["Request is empty."]}

    normalized_record = {
        "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": request},
            {"role": "assistant", "content": result.normalized},
        ]
    }
    normalized_pair = {"request": request, "dsl": result.normalized}
    return {"record": normalized_record, "pair": normalized_pair}, None


def generate_with_openai(
    model: str,
    count: int,
    output_path: Path,
    raw_text_path: Path,
    jsonl_output_path: Path,
) -> dict[str, Any]:
    load_local_env()
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set. Add the key or use --dry-run for local smoke testing.")

    prompt = build_fewshot_prompt()
    client = OpenAI()
    user_prompt = f"""
Generate exactly {count} new training examples for the OPS DSL task.

Return a JSON array only.
Each array item must be a fine-tuning-ready record with exactly this shape:
{{
  "messages": [
    {{"role": "system", "content": "{SYSTEM_INSTRUCTIONS}"}},
    {{"role": "user", "content": "natural language request"}},
    {{"role": "assistant", "content": "exact OPS DSL output"}}
  ]
}}

Constraints:
- Do not repeat the 10 examples already shown.
- Cover multiple intents and environments.
- Keep the requests realistic and concise.
- The assistant content must contain valid OPS syntax only.
- No markdown fences.
- No explanations.
"""
    response = client.responses.create(
        model=model,
        instructions=prompt,
        input=user_prompt,
        temperature=0.2,
        max_output_tokens=12000,
    )

    raw_text = response.output_text.strip()
    ensure_parent(raw_text_path)
    raw_text_path.write_text(raw_text, encoding="utf-8")
    parsed = extract_json_array(raw_text)

    valid_examples = []
    valid_records = []
    invalid_examples = []
    for item in parsed:
        normalized, invalid = normalize_record(item)
        if normalized is not None:
            valid_records.append(normalized["record"])
            valid_examples.append(normalized["pair"])
        else:
            invalid_examples.append(invalid)

    if len(valid_records) != count:
        raise ValueError(
            f"Expected exactly {count} valid fine-tuning records from gpt-4o, "
            f"but received {len(valid_records)} valid and {len(invalid_examples)} invalid."
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "openai",
        "model": model,
        "requested_count": count,
        "usage": extract_usage(response),
        "seed_examples_used": len(EXAMPLES),
        "valid_examples": valid_examples,
        "valid_records_count": len(valid_records),
        "invalid_examples": invalid_examples,
        "raw_text_path": str(raw_text_path),
        "jsonl_output_path": str(jsonl_output_path),
    }
    ensure_parent(output_path)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    write_jsonl(jsonl_output_path, valid_records)
    return payload


def generate_synthetic_examples(
    count: int,
    output_path: Path,
    raw_text_path: Path,
    jsonl_output_path: Path,
) -> dict[str, Any]:
    randomizer = Random(42)
    windows = [
        ("BUSINESS_HOURS", "during business hours"),
        ("AFTER_HOURS", "after hours"),
        ("IMMEDIATE", "immediately"),
    ]
    examples = []
    for index in range(count):
        request_template, dsl_template = SYNTHETIC_BLUEPRINTS[index % len(SYNTHETIC_BLUEPRINTS)]
        service = SERVICES[index % len(SERVICES)]
        env = ["dev", "staging", "prod", "dr"][index % 4]
        priority = ["LOW", "MEDIUM", "HIGH", "CRITICAL"][index % 4]
        approval = "MANUAL" if env in {"prod", "dr"} else "AUTO"
        notify = "NO" if index % 7 == 0 else "YES"
        window, window_phrase = windows[index % len(windows)]
        urgency_phrase = "immediately because the queue is growing" if window == "IMMEDIATE" else "during the next planned change window"
        tag = service.split("-")[0]
        request = request_template.format(
            service=service,
            env=env,
            window_phrase=window_phrase,
            urgency_phrase=urgency_phrase,
        )
        dsl = dsl_template.format(
            service=service,
            env=env,
            priority=priority,
            approval=approval,
            notify=notify,
            window=window,
            tag=tag,
        )
        examples.append({"request": request, "dsl": dsl})

    raw_text = json.dumps(examples, indent=2)
    ensure_parent(raw_text_path)
    raw_text_path.write_text(raw_text, encoding="utf-8")
    valid_records = [
        {
            "messages": [
                {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                {"role": "user", "content": example["request"]},
                {"role": "assistant", "content": example["dsl"]},
            ]
        }
        for example in examples
    ]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "dry-run",
        "model": "synthetic-local",
        "requested_count": count,
        "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        "seed_examples_used": len(EXAMPLES),
        "valid_examples": examples,
        "valid_records_count": len(valid_records),
        "invalid_examples": [],
        "raw_text_path": str(raw_text_path),
        "jsonl_output_path": str(jsonl_output_path),
    }
    ensure_parent(output_path)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    write_jsonl(jsonl_output_path, valid_records)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Phase 1 OPS DSL training data.")
    parser.add_argument("--model", default="gpt-4o", help="OpenAI model used to generate dataset examples.")
    parser.add_argument("--count", type=int, default=50, help="Number of examples to request.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/raw/generated_examples.json"),
        help="Path for the cleaned dataset artifact.",
    )
    parser.add_argument(
        "--raw-text-output",
        type=Path,
        default=Path("data/raw/generated_examples_raw.txt"),
        help="Path for the raw model text output.",
    )
    parser.add_argument(
        "--jsonl-output",
        type=Path,
        default=Path("data/raw/generated_examples.jsonl"),
        help="Path for the fine-tuning-ready JSONL records generated from GPT-4o output.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate deterministic synthetic examples locally. Useful for smoke tests, not for the final lab run.",
    )
    args = parser.parse_args()

    payload = (
        generate_synthetic_examples(args.count, args.output, args.raw_text_output, args.jsonl_output)
        if args.dry_run
        else generate_with_openai(args.model, args.count, args.output, args.raw_text_output, args.jsonl_output)
    )
    print(json.dumps(
        {
            "mode": payload["mode"],
            "valid_examples": len(payload["valid_examples"]),
            "invalid_examples": len(payload["invalid_examples"]),
            "output": str(args.output),
            "jsonl_output": str(args.jsonl_output),
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()
