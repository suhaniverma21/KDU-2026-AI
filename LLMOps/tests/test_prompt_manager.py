"""Tests for prompt management."""

from pathlib import Path

import pytest

from src.config_loader import load_all_config
from src.prompt_manager import PromptNotFoundError, load_prompt, load_prompt_registry


def test_load_prompt_registry_returns_prompt_config() -> None:
    registry = load_prompt_registry()

    assert "prompts" in registry
    assert registry["prompts"]["FAQ"]["prompt_id"] == "faq"


def test_load_prompt_by_prompt_id_returns_content_and_metadata() -> None:
    result = load_prompt("faq")

    assert result["prompt_id"] == "faq"
    assert result["version"] == "v2"
    assert result["category"] == "FAQ"
    assert "Lead with the direct answer" in result["content"]
    assert result["fallback_applied"] is False


def test_load_prompt_by_category_name_returns_booking_prompt() -> None:
    result = load_prompt("booking")

    assert result["prompt_id"] == "booking"
    assert result["category"] == "booking"
    assert "schedule, reschedule, cancel, or confirm appointments" in result["content"]


def test_load_prompt_uses_fallback_version_when_requested_version_is_missing() -> None:
    config = load_all_config()

    result = load_prompt("complaint", version="v3", config=config)

    assert result["prompt_id"] == "complaint"
    assert result["version"] == "v1"
    assert result["fallback_applied"] is True


def test_load_prompt_uses_configured_current_version_without_code_changes() -> None:
    config = load_all_config()

    result = load_prompt("complaint", config=config)

    assert result["version"] == "v2"
    assert "natural and respectful way" in result["content"]


def test_load_prompt_supports_switching_current_version_through_config_only() -> None:
    config = load_all_config()
    config["prompts"]["prompts"]["FAQ"]["current_version"] = "v1"

    result = load_prompt("FAQ", config=config)

    assert result["version"] == "v1"
    assert "Give concise, accurate, customer-friendly answers." in result["content"]


def test_load_prompt_raises_for_unknown_prompt() -> None:
    with pytest.raises(PromptNotFoundError, match="not defined in the prompt registry"):
        load_prompt("unknown_prompt")


def test_load_prompt_raises_when_prompt_file_is_missing(tmp_path: Path) -> None:
    config = load_all_config()
    config["prompts"]["prompts"]["FAQ"]["versions"]["v1"]["file"] = "missing_faq_v1.txt"

    with pytest.raises(PromptNotFoundError, match="Prompt file not found"):
        load_prompt("FAQ", config=config, prompts_dir=tmp_path)
