"""Runs the full Phase 1 real-time voice pipeline from microphone to spoken response."""

from __future__ import annotations

import sys
from typing import Any

from config.settings import get_settings
from orchestration.voice_pipeline import run_phase1_pipeline


def main() -> int:
    """Run the full Phase 1 pipeline and return a clean process exit code."""
    try:
        settings = get_settings()
        print("Starting Phase 1 voice pipeline...")
        print(
            "Audio config:"
            f" sample_rate={settings.voice_sample_rate},"
            f" chunk_size={settings.voice_chunk_size},"
            f" silence_threshold={settings.voice_silence_threshold},"
            f" silence_duration={settings.voice_silence_duration_seconds}s"
        )
        print("Speak a billing-style request into your microphone.")
        if settings.voice_interrupt_enabled:
            print("Interruption mode is enabled. Use headphones to avoid speaker echo.")
            print("If TTS starts replying, you can interrupt by speaking again.")
            print(
                "Only meaningful interruptions are accepted:"
                f" activation_chunks={settings.voice_interrupt_activation_chunks},"
                f" min_chars={settings.voice_interrupt_min_chars},"
                f" max_restarts={settings.voice_interrupt_max_restarts}"
            )
        else:
            print("Interruption mode is disabled by default for reliable speaker playback.")
            print("Set VOICE_INTERRUPT_ENABLED=true in .env to test live interruption.")

        result = run_phase1_pipeline(settings)
        _print_result_summary(result)
        return 0
    except Exception as exc:
        print(f"[Error] Phase 1 pipeline failed: {exc}", file=sys.stderr)
        return 1


def _print_result_summary(result: dict[str, Any]) -> None:
    """Print the key handoff and billing response details after the pipeline finishes."""
    print("\nPhase 1 completed.")
    print(f"Resolved intent: {result.get('intent', 'unknown')}")
    print(f"Original message: {result.get('original_message', '')}")
    print(f"Billing response: {result.get('response_text', '')}")
    print("Updated conversation history:")
    for turn in result.get("conversation_history", []):
        role = turn.get("role", "unknown")
        content = turn.get("content", "")
        print(f"- {role}: {content}")


if __name__ == "__main__":
    raise SystemExit(main())
