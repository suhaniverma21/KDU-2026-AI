"""Tests for the interactive FixIt CLI helpers."""

from __future__ import annotations

from src.cli import render_result, summarize_fallbacks


def test_render_result_shows_human_readable_sections() -> None:
    result = {
        "response_text": "Here is your answer.",
        "metadata": {
            "query": "Can I reschedule my cleaning appointment?",
            "classification": {
                "category": "booking",
                "complexity": "medium",
                "confidence": 0.82,
            },
            "route": {"selected_tier": "medium"},
            "model": {"name": "gemini-2.5-flash"},
            "fallback": {"applied": False, "events": []},
        },
    }

    rendered = render_result(result, debug=False)

    assert "FixIt Support Result" in rendered
    assert "Category: booking" in rendered
    assert "Complexity: medium" in rendered
    assert "Confidence: 0.82" in rendered
    assert "Selected Tier: medium" in rendered
    assert "Response: Here is your answer." in rendered


def test_render_result_in_no_llm_mode_uses_skip_reason() -> None:
    result = {
        "response_text": "LLM generation was skipped.",
        "metadata": {
            "query": "Help me with something.",
            "classification": {
                "category": "FAQ",
                "complexity": "medium",
                "confidence": 0.0,
            },
            "route": {"selected_tier": "medium"},
            "model": {},
            "fallback": {
                "applied": True,
                "events": [
                    {
                        "fallback_reason": "Classification remains unresolved; using safe routing tier 'medium'."
                    }
                ],
            },
            "llm_generation_skipped": True,
            "skip_reason": "All live LLM calls were skipped by CLI flag, including the secondary classifier.",
        },
    }

    rendered = render_result(result, debug=False)

    assert "Response: All live LLM calls were skipped by CLI flag" in rendered
    assert "Fallback:" in rendered


def test_summarize_fallbacks_deduplicates_reasons() -> None:
    summary = summarize_fallbacks(
        [
            {"fallback_reason": "Low-confidence classification routed safely."},
            {"fallback_reason": "Low-confidence classification routed safely."},
            {"fallback_reason": "Budget hard limit reached."},
        ]
    )

    assert summary == "Low-confidence classification routed safely. | Budget hard limit reached."
