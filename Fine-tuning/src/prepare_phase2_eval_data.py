from __future__ import annotations

import argparse
import json
from pathlib import Path
from random import Random

from dsl_spec import SYSTEM_INSTRUCTIONS
from validate_dsl import validate_dsl


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def load_examples(path: Path) -> list[dict[str, str]]:
    examples = []
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
                examples.append({"request": request, "dsl": result.normalized})
    return examples


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
    parser = argparse.ArgumentParser(description="Prepare the Phase 2 train/validation split.")
    parser.add_argument("--input", type=Path, default=Path("data/raw/generated_examples.jsonl"))
    parser.add_argument("--train-output", type=Path, default=Path("data/processed/phase2_train.jsonl"))
    parser.add_argument("--validation-output", type=Path, default=Path("data/processed/validation.jsonl"))
    parser.add_argument("--summary-output", type=Path, default=Path("data/processed/phase2_split_summary.json"))
    parser.add_argument("--validation-size", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    examples = load_examples(args.input)
    if len(examples) <= args.validation_size:
        raise ValueError(
            f"Need more than {args.validation_size} valid examples to create both training and validation splits."
        )

    randomizer = Random(args.seed)
    randomizer.shuffle(examples)

    validation_examples = examples[: args.validation_size]
    training_examples = examples[args.validation_size :]

    train_records = [to_record(item["request"], item["dsl"]) for item in training_examples]
    validation_records = [to_record(item["request"], item["dsl"]) for item in validation_examples]

    write_jsonl(args.train_output, train_records)
    write_jsonl(args.validation_output, validation_records)

    summary = {
        "total_valid_examples": len(examples),
        "phase2_train_examples": len(train_records),
        "validation_examples": len(validation_records),
        "train_output": str(args.train_output),
        "validation_output": str(args.validation_output),
    }
    ensure_parent(args.summary_output)
    args.summary_output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
