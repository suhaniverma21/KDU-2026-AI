from __future__ import annotations

import argparse
import json
from pathlib import Path

from dsl_spec import HOLDOUT_CASES, SYSTEM_INSTRUCTIONS
from validate_dsl import validate_dsl


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def load_examples(path: Path) -> list[dict[str, str]]:
    if path.suffix.lower() == ".jsonl":
        cleaned = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                messages = record["messages"]
                user_message = next(message for message in messages if message["role"] == "user")
                assistant_message = next(message for message in messages if message["role"] == "assistant")
                request = user_message["content"].strip()
                dsl = assistant_message["content"].strip()
                result = validate_dsl(dsl)
                if result.is_valid and request:
                    cleaned.append({"request": request, "dsl": result.normalized})
        return cleaned

    payload = json.loads(path.read_text(encoding="utf-8"))
    examples = payload.get("valid_examples", payload)
    cleaned = []
    for example in examples:
        request = example["request"].strip()
        dsl = example["dsl"].strip()
        result = validate_dsl(dsl)
        if result.is_valid and request:
            cleaned.append({"request": request, "dsl": result.normalized})
    return cleaned


def to_record(request: str, dsl: str) -> dict:
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": request},
            {"role": "assistant", "content": dsl},
        ]
    }


def write_jsonl(path: Path, records: list[dict]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare Phase 1 fine-tuning data using all generated examples.")
    parser.add_argument("--input", type=Path, default=Path("data/raw/generated_examples.jsonl"))
    parser.add_argument("--train-output", type=Path, default=Path("data/processed/train.jsonl"))
    parser.add_argument("--bad-sample-output", type=Path, default=Path("data/processed/train_bad_sample.jsonl"))
    parser.add_argument("--holdout-output", type=Path, default=Path("data/processed/phase1_holdout.json"))
    parser.add_argument("--summary-output", type=Path, default=Path("data/processed/dataset_summary.json"))
    args = parser.parse_args()

    examples = load_examples(args.input)
    train_records = [to_record(item["request"], item["dsl"]) for item in examples]
    bad_sample_records = list(train_records)
    contaminated = dict(bad_sample_records[0])
    contaminated_messages = list(contaminated["messages"])
    contaminated_messages[-1] = {
        "role": "assistant",
        "content": f"```dsl\n{contaminated_messages[-1]['content']}\n```",
    }
    contaminated["messages"] = contaminated_messages
    bad_sample_records[0] = contaminated

    write_jsonl(args.train_output, train_records)
    write_jsonl(args.bad_sample_output, bad_sample_records)

    holdout_payload = [{"request": item.request, "expected_dsl": item.dsl} for item in HOLDOUT_CASES]
    ensure_parent(args.holdout_output)
    args.holdout_output.write_text(json.dumps(holdout_payload, indent=2), encoding="utf-8")

    summary = {
        "total_valid_examples": len(examples),
        "train_examples": len(train_records),
        "bad_sample_variant_examples": len(bad_sample_records),
        "contaminated_record_index": 0,
        "train_output": str(args.train_output),
        "bad_sample_output": str(args.bad_sample_output),
        "holdout_output": str(args.holdout_output),
    }
    ensure_parent(args.summary_output)
    args.summary_output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
