"""Tests for configuration loading."""

from pathlib import Path
import textwrap

import pytest

from src.config_loader import ConfigValidationError, load_all_config, load_yaml_file, validate_config


def test_load_all_config_returns_valid_project_config() -> None:
    config = load_all_config()
    assert set(config) == {"classifier", "models", "routing", "prompts", "feature_flags", "cost_limits"}
    assert config["models"]["models"]["cheap"]["provider"] == "google_ai_studio"
    assert config["routing"]["routing_rules"]["FAQ"]["low"] == "cheap"
    assert config["classifier"]["classifier"]["stage2"]["model_tier"] == "cheap"


def test_load_yaml_file_reads_mapping_from_disk(tmp_path: Path) -> None:
    config_file = tmp_path / "example.yaml"
    config_file.write_text("sample:\n  enabled: true\n", encoding="utf-8")

    result = load_yaml_file(config_file)

    assert result == {"sample": {"enabled": True}}


def test_load_yaml_file_raises_for_missing_file(tmp_path: Path) -> None:
    missing_file = tmp_path / "missing.yaml"

    with pytest.raises(ConfigValidationError, match="Configuration file not found"):
        load_yaml_file(missing_file)


def test_load_yaml_file_raises_for_invalid_yaml(tmp_path: Path) -> None:
    config_file = tmp_path / "invalid.yaml"
    config_file.write_text("models: [broken\n", encoding="utf-8")

    with pytest.raises(ConfigValidationError, match="Invalid YAML"):
        load_yaml_file(config_file)


def test_validate_config_raises_for_missing_required_section() -> None:
    incomplete_config = {
        "classifier": {"classifier": load_all_config()["classifier"]["classifier"]},
        "models": {"models": {"cheap": {"provider": "google_ai_studio", "model_name": "gemini-2.5-flash-lite", "max_queries_percent": 70}}},
    }

    with pytest.raises(ConfigValidationError, match="Missing required config section: routing"):
        validate_config(incomplete_config)


def test_validate_config_raises_for_missing_required_nested_key() -> None:
    invalid_config = {
        "classifier": {"classifier": load_all_config()["classifier"]["classifier"]},
        "models": {"models": {"cheap": {"provider": "google_ai_studio", "model_name": "gemini-2.5-flash-lite"}}},
        "routing": {"routing_rules": {"FAQ": {"low": "cheap", "medium": "cheap", "high": "medium"}}},
        "prompts": {"prompts": {"FAQ": {"prompt_id": "faq", "current_version": "v1", "fallback_version": "v1", "versions": {"v1": {"file": "faq_v1.txt"}}}}},
        "feature_flags": {
            "feature_flags": {
                "enable_fallback": True,
                "enable_prompt_versioning": True,
                "enable_budget_guardrail": True,
            }
        },
        "cost_limits": {
            "cost_limits": {
                "monthly_budget_usd": 500,
                "warning_threshold_usd": 400,
                "hard_limit_usd": 500,
            }
        },
    }

    with pytest.raises(ConfigValidationError, match="missing required keys: max_queries_percent"):
        validate_config(invalid_config)


def test_load_all_config_raises_for_invalid_config_directory(tmp_path: Path) -> None:
    config_contents = {
        "classifier.yaml": """
        classifier:
          taxonomy:
            categories: [FAQ, booking, complaint]
            complexity_levels: [low, medium, high]
          stage1:
            direct_accept_confidence: 0.85
            escalation_confidence_threshold: 0.6
            minimum_rule_hits_for_direct_accept: 2
            minimum_margin_for_direct_accept: 2
          stage2:
            enabled: true
            model_tier: cheap
            max_retries: 1
          fallback:
            on_llm_failure: unresolved_safe_route
            unresolved_complexity: medium
            unresolved_confidence: 0.0
        """,
        "models.yaml": """
        models:
          cheap:
            provider: google_ai_studio
            model_name: gemini-2.5-flash-lite
            max_queries_percent: 70
        """,
        "routing.yaml": """
        routing_rules:
          FAQ:
            low: cheap
            medium: cheap
            high: medium
        """,
        "prompts.yaml": """
        prompts:
          FAQ:
            prompt_id: faq
            active_version: v1
            fallback_version: v1
        """,
        "feature_flags.yaml": """
        feature_flags:
          enable_fallback: true
          enable_prompt_versioning: true
          enable_budget_guardrail: true
        """,
        "cost_limits.yaml": """
        cost_limits:
          monthly_budget_usd: 500
          warning_threshold_usd: 400
          hard_limit_usd: 500
        """,
    }

    for file_name, content in config_contents.items():
        (tmp_path / file_name).write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")

    (tmp_path / "routing.yaml").write_text(
        textwrap.dedent(
            """
            routing_rules:
              FAQ:
                low: cheap
                medium: cheap
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigValidationError, match="missing complexity levels: high"):
        load_all_config(tmp_path)


def test_validate_config_raises_for_invalid_default_prompt_reference() -> None:
    config = load_all_config()
    config["prompts"]["default_prompt"]["version"] = "v99"

    with pytest.raises(ConfigValidationError, match="default_prompt references undefined version"):
        validate_config(config)


def test_validate_config_raises_for_unknown_routing_tier_reference() -> None:
    config = load_all_config()
    config["routing"]["routing_rules"]["FAQ"]["low"] = "ultra"

    with pytest.raises(ConfigValidationError, match="references unknown model tier 'ultra'"):
        validate_config(config)


def test_validate_config_raises_for_invalid_cost_limit_ordering() -> None:
    config = load_all_config()
    config["cost_limits"]["cost_limits"]["warning_threshold_usd"] = 600

    with pytest.raises(ConfigValidationError, match="warning_threshold_usd cannot exceed hard_limit_usd"):
        validate_config(config)


def test_validate_config_raises_for_invalid_classifier_model_tier_reference() -> None:
    config = load_all_config()
    config["classifier"]["classifier"]["stage2"]["model_tier"] = "ultra"

    with pytest.raises(ConfigValidationError, match="Classifier stage2 model_tier references unknown model tier"):
        validate_config(config)
