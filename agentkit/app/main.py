from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv

from app.logging_utils import StructuredLogger
from app.phase4 import build_sample_transaction_document
from app.sdk_types import HandoffPayload


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", choices=["phase1", "phase2", "phase3", "phase4", "phase5"], required=True)
    parser.add_argument(
        "--prompt",
        default="Count the active users",
    )
    parser.add_argument(
        "--log-file",
        default="logs/phase1.jsonl",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=8,
    )
    parser.add_argument(
        "--stop-after-steps",
        type=int,
        default=None,
    )
    args = parser.parse_args()

    try:
        from app.openai_sdk_app import (
            Phase1SDKApp,
            Phase2SDKApp,
            Phase3SDKApp,
            Phase4SDKApp,
            Phase5SDKApp,
        )

        if args.demo == "phase1":
            harness = Phase1SDKApp(logger=StructuredLogger(Path(args.log_file)))
            outcome = harness.run(
                prompt=args.prompt,
                session_id="phase1-sdk",
                max_turns=args.max_attempts,
            )
        elif args.demo == "phase2":
            harness = Phase2SDKApp()
            outcome = harness.run(
                prompt=args.prompt
                if args.prompt != "Count the active users"
                else "What is John's salary and how much PTO does he have?"
            )
        elif args.demo == "phase3":
            harness = Phase3SDKApp()
            payload = HandoffPayload(
                session_id="phase3-sdk",
                user_id="user_456",
                source_agent="coordinator_agent",
                target_agent="finance_agent",
                task_type="update_banking_details",
                user_intent="Update banking details",
                entities={
                    "routing_number": "123456789",
                    "account_number": None,
                    "account_holder_name": None,
                },
                required_fields=[
                    "routing_number",
                    "account_number",
                    "account_holder_name",
                ],
            )
            outcome = harness.run(
                prompt=args.prompt
                if args.prompt != "Count the active users"
                else "Update my banking details. Routing number is 123456789.",
                payload=payload,
            )
        elif args.demo == "phase4":
            harness = Phase4SDKApp(logger=StructuredLogger(Path(args.log_file)))
            outcome = harness.run(
                document=args.prompt
                if args.prompt != "Count the active users"
                else build_sample_transaction_document(),
                follow_up_messages=["okay", "cool", "sounds good"],
            )
        else:
            harness = Phase5SDKApp()
            outcome = harness.run(
                goal="Prepare a concise monthly expense review for the operations team.",
                execution_bundle={
                    "session_summary": "Compile a quick monthly expense review for operations.",
                    "case_facts": {
                        "reporting_period": "2026-04",
                        "department": "Operations",
                        "expenses": [
                            {"category": "Cloud Hosting", "amount_usd": 4200},
                            {"category": "Support Contractors", "amount_usd": 2800},
                            {"category": "Software Licenses", "amount_usd": 950},
                        ],
                        "budget_limit_usd": 9000,
                    },
                    "flags": [],
                    "completed_steps": [],
                },
                session_id="phase5-sdk",
                trace_id="trace-phase5-sdk",
            )
    except RuntimeError as exc:
        print(json.dumps({"error": str(exc), "backend": "sdk"}, indent=2))
        raise SystemExit(1) from exc

    print(json.dumps(asdict(outcome), indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
