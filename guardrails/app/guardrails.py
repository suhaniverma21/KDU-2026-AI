import asyncio
from pathlib import Path
from time import perf_counter

from langsmith import traceable
from nemoguardrails.actions.action_dispatcher import ActionDispatcher


class Phase1Guardrails:
    def __init__(self) -> None:
        self.backend_name = "nemo-guardrails"
        base_path = Path(__file__).resolve().parent.parent / "nemo_guardrails"
        self.input_dispatcher = ActionDispatcher(config_path=str(base_path / "input"))
        self.output_dispatcher = ActionDispatcher(config_path=str(base_path / "output"))

    @traceable(run_type="tool", name="phase1_input_guardrail")
    def inspect_input(self, user_message: str) -> tuple[bool, str | None, float]:
        start = perf_counter()
        result, status = asyncio.run(
            self.input_dispatcher.execute_action(
                "detect_prompt_injection",
                {"text": user_message},
            )
        )
        latency_ms = round((perf_counter() - start) * 1000, 3)

        if status == "success" and bool(result):
            return True, "Blocked by NeMo input rails", latency_ms

        return False, None, latency_ms

    @traceable(run_type="tool", name="phase1_output_guardrail")
    def inspect_output(
        self, user_message: str, raw_response: str
    ) -> tuple[str, bool, str | None, float]:
        start = perf_counter()
        should_block, block_status = asyncio.run(
            self.output_dispatcher.execute_action(
                "should_block_output",
                {"user_message": user_message, "bot_message": raw_response},
            )
        )
        if block_status != "success":
            raise RuntimeError("NeMo output guard action failed.")

        latency_ms = round((perf_counter() - start) * 1000, 3)

        blocked_message = (
            "I can help with account questions, but I can't reveal full stored personal data."
        )
        if bool(should_block):
            return blocked_message, True, "Blocked by NeMo output rails", latency_ms

        redacted_output, redact_status = asyncio.run(
            self.output_dispatcher.execute_action(
                "redact_output",
                {"user_message": user_message, "bot_message": raw_response},
            )
        )
        if redact_status != "success":
            raise RuntimeError("NeMo output redaction action failed.")

        if redacted_output != raw_response:
            return str(redacted_output), False, "Modified by NeMo output rails", latency_ms

        return raw_response, False, None, latency_ms
