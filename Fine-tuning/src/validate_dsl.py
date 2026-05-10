from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


DSL_PATTERN = re.compile(
    r'^OPS\|'
    r'INTENT=(DEPLOY|SCALE|RESTART|BACKUP|RESTORE|PATCH|BLOCK|MIGRATE|FAILOVER|ROLLBACK)\|'
    r'SERVICE="([a-z0-9-]+)"\|'
    r'ENV="(dev|staging|prod|dr)"\|'
    r'PRIORITY=(LOW|MEDIUM|HIGH|CRITICAL)\|'
    r'APPROVAL=(AUTO|MANUAL)\|'
    r'NOTIFY=(YES|NO)\|'
    r'WINDOW="(IMMEDIATE|BUSINESS_HOURS|AFTER_HOURS|MAINTENANCE_SAT_0200Z|MAINTENANCE_SUN_0100Z)"\|'
    r'TAGS=\[(?:"[a-z0-9-]+"(?:,"[a-z0-9-]+"){0,2})\]$'
)


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[str]
    normalized: str


def validate_dsl(text: str) -> ValidationResult:
    if text is None:
        return ValidationResult(False, ["DSL output is missing."], "")

    normalized = text.strip()
    errors: list[str] = []

    if not normalized:
        errors.append("DSL output is empty.")
        return ValidationResult(False, errors, normalized)

    if "```" in normalized:
        errors.append("Markdown code fences are not allowed.")

    if "\n" in normalized or "\r" in normalized:
        errors.append("Output must be a single line.")

    if normalized.lower().startswith(("sure", "here", "output", "dsl:", "result:")):
        errors.append("Conversational filler is not allowed.")

    if not normalized.startswith("OPS|"):
        errors.append('Output must start with "OPS|".')

    if not DSL_PATTERN.fullmatch(normalized):
        errors.append("Output does not match the required OPS DSL format.")

    return ValidationResult(not errors, errors, normalized)


def validate_json_records(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    examples = payload.get("valid_examples", payload)
    results = []
    for item in examples:
        result = validate_dsl(item["dsl"])
        row = {"request": item["request"], "dsl": item["dsl"], **asdict(result)}
        results.append(row)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate OPS DSL strings or dataset files.")
    parser.add_argument("--text", help="Validate a single DSL string.")
    parser.add_argument("--file", type=Path, help="Validate a JSON dataset file.")
    args = parser.parse_args()

    if args.text:
        print(json.dumps(asdict(validate_dsl(args.text)), indent=2))
        return

    if args.file:
        print(json.dumps(validate_json_records(args.file), indent=2))
        return

    parser.error("Provide either --text or --file.")


if __name__ == "__main__":
    main()
