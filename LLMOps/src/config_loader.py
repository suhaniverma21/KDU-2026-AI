"""Configuration loading utilities for the FixIt LLMOps system."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import yaml


CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
CONFIG_FILES = {
    "classifier": "classifier.yaml",
    "models": "models.yaml",
    "routing": "routing.yaml",
    "prompts": "prompts.yaml",
    "feature_flags": "feature_flags.yaml",
    "cost_limits": "cost_limits.yaml",
}

REQUIRED_SECTION_KEYS = {
    "classifier": ("classifier",),
    "models": ("models",),
    "routing": ("routing_rules",),
    "prompts": ("prompts",),
    "feature_flags": ("feature_flags",),
    "cost_limits": ("cost_limits",),
}


class ConfigValidationError(ValueError):
    """Raised when configuration files are missing or invalid."""


def load_yaml_file(path: str | Path) -> dict[str, Any]:
    """Load a YAML configuration file and return its parsed mapping."""
    file_path = Path(path)

    if not file_path.exists():
        raise ConfigValidationError(f"Configuration file not found: {file_path}")

    try:
        with file_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except yaml.YAMLError as exc:
        raise ConfigValidationError(f"Invalid YAML in configuration file {file_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigValidationError(f"Configuration file must contain a top-level mapping: {file_path}")

    return data


def load_all_config(config_dir: str | Path = CONFIG_DIR) -> dict[str, Any]:
    """Load, validate, and return all project configuration."""
    base_path = Path(config_dir)
    config = {
        section_name: load_yaml_file(base_path / file_name)
        for section_name, file_name in CONFIG_FILES.items()
    }
    validate_config(config)
    return config


def validate_config(config: dict[str, Any]) -> None:
    """Validate the presence and shape of all required configuration sections."""
    for section_name, required_keys in REQUIRED_SECTION_KEYS.items():
        if section_name not in config:
            raise ConfigValidationError(f"Missing required config section: {section_name}")

        section = config[section_name]
        if not isinstance(section, dict):
            raise ConfigValidationError(
                f"Config section '{section_name}' must be a mapping, got {type(section).__name__}."
            )

        for key in required_keys:
            if key not in section:
                raise ConfigValidationError(
                    f"Config section '{section_name}' is missing required key '{key}'."
                )

            if not isinstance(section[key], dict):
                raise ConfigValidationError(
                    f"Config key '{section_name}.{key}' must be a mapping, got {type(section[key]).__name__}."
                )

            if not section[key]:
                raise ConfigValidationError(f"Config key '{section_name}.{key}' cannot be empty.")

    _validate_models(config["models"]["models"])
    _validate_classifier(config["classifier"]["classifier"])
    _validate_routing(config["routing"]["routing_rules"])
    _validate_prompts(config["prompts"]["prompts"])
    _validate_feature_flags(config["feature_flags"]["feature_flags"])
    _validate_cost_limits(config["cost_limits"]["cost_limits"])
    _validate_cross_config_consistency(config)


def _validate_models(models: dict[str, Any]) -> None:
    required_model_keys = {"provider", "model_name", "max_queries_percent"}
    total_percent = 0.0

    for tier_name, model_config in models.items():
        if not isinstance(model_config, dict):
            raise ConfigValidationError(f"Model tier '{tier_name}' must map to a configuration object.")

        missing_keys = required_model_keys - set(model_config)
        if missing_keys:
            missing = ", ".join(sorted(missing_keys))
            raise ConfigValidationError(f"Model tier '{tier_name}' is missing required keys: {missing}.")

        if not str(model_config["provider"]).strip():
            raise ConfigValidationError(f"Model tier '{tier_name}' must define a non-empty provider.")
        if not str(model_config["model_name"]).strip():
            raise ConfigValidationError(f"Model tier '{tier_name}' must define a non-empty model_name.")

        max_queries_percent = model_config["max_queries_percent"]
        if not isinstance(max_queries_percent, (int, float)):
            raise ConfigValidationError(f"Model tier '{tier_name}' max_queries_percent must be numeric.")
        if max_queries_percent < 0:
            raise ConfigValidationError(f"Model tier '{tier_name}' max_queries_percent cannot be negative.")
        total_percent += float(max_queries_percent)

    if total_percent > 100:
        raise ConfigValidationError("Combined model max_queries_percent cannot exceed 100.")


def _validate_routing(routing_rules: dict[str, Any]) -> None:
    required_complexities = {"low", "medium", "high"}

    for category, rules in routing_rules.items():
        if not isinstance(rules, dict):
            raise ConfigValidationError(f"Routing rules for category '{category}' must be a mapping.")

        missing_complexities = required_complexities - set(rules)
        if missing_complexities:
            missing = ", ".join(sorted(missing_complexities))
            raise ConfigValidationError(
                f"Routing rules for category '{category}' are missing complexity levels: {missing}."
            )


def _validate_classifier(classifier_config: dict[str, Any]) -> None:
    required_sections = {"taxonomy", "stage1", "stage2", "fallback"}
    missing_sections = required_sections - set(classifier_config)
    if missing_sections:
        missing = ", ".join(sorted(missing_sections))
        raise ConfigValidationError(f"Classifier config is missing required sections: {missing}.")

    taxonomy = classifier_config["taxonomy"]
    categories = taxonomy.get("categories")
    complexity_levels = taxonomy.get("complexity_levels")
    if categories != ["FAQ", "booking", "complaint"]:
        raise ConfigValidationError("Classifier categories must remain exactly: FAQ, booking, complaint.")
    if complexity_levels != ["low", "medium", "high"]:
        raise ConfigValidationError("Classifier complexity_levels must remain exactly: low, medium, high.")

    stage1 = classifier_config["stage1"]
    for threshold_name in ("direct_accept_confidence", "escalation_confidence_threshold"):
        threshold_value = stage1.get(threshold_name)
        if not isinstance(threshold_value, (int, float)):
            raise ConfigValidationError(f"Classifier stage1 threshold '{threshold_name}' must be numeric.")
        if threshold_value < 0 or threshold_value > 1:
            raise ConfigValidationError(f"Classifier stage1 threshold '{threshold_name}' must be between 0 and 1.")

    if stage1["direct_accept_confidence"] < stage1["escalation_confidence_threshold"]:
        raise ConfigValidationError(
            "Classifier direct_accept_confidence must be greater than or equal to escalation_confidence_threshold."
        )

    stage2 = classifier_config["stage2"]
    if not isinstance(stage2.get("enabled"), bool):
        raise ConfigValidationError("Classifier stage2 enabled flag must be boolean.")
    if not isinstance(stage2.get("max_retries"), int) or stage2["max_retries"] < 0:
        raise ConfigValidationError("Classifier stage2 max_retries must be a non-negative integer.")

    fallback = classifier_config["fallback"]
    if fallback.get("on_llm_failure") not in {"unresolved_safe_route"}:
        raise ConfigValidationError("Classifier fallback on_llm_failure currently supports only unresolved_safe_route.")
    if fallback.get("unresolved_complexity") not in {"low", "medium", "high"}:
        raise ConfigValidationError("Classifier fallback unresolved_complexity must be low, medium, or high.")
    unresolved_confidence = fallback.get("unresolved_confidence")
    if not isinstance(unresolved_confidence, (int, float)) or unresolved_confidence < 0 or unresolved_confidence > 1:
        raise ConfigValidationError("Classifier fallback unresolved_confidence must be between 0 and 1.")


def _validate_prompts(prompts: dict[str, Any]) -> None:
    required_prompt_keys = {"prompt_id", "fallback_version", "versions"}

    for category, prompt_config in prompts.items():
        if not isinstance(prompt_config, dict):
            raise ConfigValidationError(f"Prompt config for category '{category}' must be a mapping.")

        missing_keys = required_prompt_keys - set(prompt_config)
        if missing_keys:
            missing = ", ".join(sorted(missing_keys))
            raise ConfigValidationError(
                f"Prompt config for category '{category}' is missing required keys: {missing}."
            )

        current_version = prompt_config.get("current_version", prompt_config.get("active_version"))
        if not current_version:
            raise ConfigValidationError(
                f"Prompt config for category '{category}' must define 'current_version' or legacy 'active_version'."
            )

        versions = prompt_config["versions"]
        if not isinstance(versions, dict) or not versions:
            raise ConfigValidationError(f"Prompt config for category '{category}' must include version mappings.")

        if current_version not in versions:
            raise ConfigValidationError(
                f"Prompt config for category '{category}' references undefined current version '{current_version}'."
            )

        if prompt_config["fallback_version"] not in versions:
            raise ConfigValidationError(
                f"Prompt config for category '{category}' references undefined fallback version "
                f"'{prompt_config['fallback_version']}'."
            )


def _validate_feature_flags(feature_flags: dict[str, Any]) -> None:
    required_flags = {"enable_fallback", "enable_prompt_versioning", "enable_budget_guardrail"}
    missing_flags = required_flags - set(feature_flags)

    if missing_flags:
        missing = ", ".join(sorted(missing_flags))
        raise ConfigValidationError(f"Feature flags are missing required keys: {missing}.")

    for flag_name, flag_value in feature_flags.items():
        if not isinstance(flag_value, bool):
            raise ConfigValidationError(f"Feature flag '{flag_name}' must be a boolean.")


def _validate_cost_limits(cost_limits: dict[str, Any]) -> None:
    required_limits = {"monthly_budget_usd", "warning_threshold_usd", "hard_limit_usd"}
    missing_limits = required_limits - set(cost_limits)

    if missing_limits:
        missing = ", ".join(sorted(missing_limits))
        raise ConfigValidationError(f"Cost limits are missing required keys: {missing}.")

    for limit_name, limit_value in cost_limits.items():
        if not isinstance(limit_value, (int, float)):
            raise ConfigValidationError(f"Cost limit '{limit_name}' must be numeric.")
        if limit_value < 0:
            raise ConfigValidationError(f"Cost limit '{limit_name}' cannot be negative.")

    if cost_limits["warning_threshold_usd"] > cost_limits["hard_limit_usd"]:
        raise ConfigValidationError("warning_threshold_usd cannot exceed hard_limit_usd.")
    if cost_limits["hard_limit_usd"] > cost_limits["monthly_budget_usd"]:
        raise ConfigValidationError("hard_limit_usd cannot exceed monthly_budget_usd.")


def _validate_cross_config_consistency(config: dict[str, Any]) -> None:
    """Validate references that span multiple config sections."""
    model_tiers = set(config["models"]["models"])
    prompts = config["prompts"]["prompts"]
    classifier_config = config["classifier"]["classifier"]
    default_prompt = config["prompts"].get("default_prompt", {})
    routing_config = config["routing"]
    routing_rules = routing_config["routing_rules"]
    routing_defaults = routing_config.get("defaults", {})
    budget_guardrails = routing_config.get("budget_guardrails", {})

    _validate_default_prompt(default_prompt, prompts)
    _validate_routing_tier_references(routing_rules, routing_defaults, budget_guardrails, model_tiers)
    _validate_classifier_references(classifier_config, model_tiers)


def _validate_default_prompt(default_prompt: dict[str, Any], prompts: dict[str, Any]) -> None:
    prompt_id = default_prompt.get("prompt_id")
    version = default_prompt.get("version")
    if not prompt_id or not version:
        raise ConfigValidationError("default_prompt must define both prompt_id and version.")

    for prompt_entry in prompts.values():
        if prompt_entry.get("prompt_id") == prompt_id:
            if version not in prompt_entry.get("versions", {}):
                raise ConfigValidationError(
                    f"default_prompt references undefined version '{version}' for prompt '{prompt_id}'."
                )
            return

    raise ConfigValidationError(f"default_prompt references unknown prompt_id '{prompt_id}'.")


def _validate_routing_tier_references(
    routing_rules: dict[str, Any],
    routing_defaults: dict[str, Any],
    budget_guardrails: dict[str, Any],
    model_tiers: set[str],
) -> None:
    for category, rules in routing_rules.items():
        for complexity, tier in rules.items():
            if tier not in model_tiers:
                raise ConfigValidationError(
                    f"Routing rule '{category}.{complexity}' references unknown model tier '{tier}'."
                )

    default_tier_fields = (
        "low_confidence_tier",
        "unavailable_model_fallback_tier",
        "budget_exceeded_fallback_tier",
    )
    for field_name in default_tier_fields:
        tier = routing_defaults.get(field_name)
        if tier is not None and tier not in model_tiers:
            raise ConfigValidationError(
                f"Routing defaults field '{field_name}' references unknown model tier '{tier}'."
            )

    warning_tier = budget_guardrails.get("warning", {}).get("premium_downgrade_tier")
    if warning_tier is not None and warning_tier not in model_tiers:
        raise ConfigValidationError(
            f"Budget guardrail warning premium_downgrade_tier references unknown model tier '{warning_tier}'."
        )

    hard_limit_policy = budget_guardrails.get("hard_limit", {})
    hard_limit_tier = hard_limit_policy.get("default_fallback_tier")
    if hard_limit_tier is not None and hard_limit_tier not in model_tiers:
        raise ConfigValidationError(
            f"Budget guardrail hard_limit default_fallback_tier references unknown model tier '{hard_limit_tier}'."
        )

    for category, rules in hard_limit_policy.get("safe_category_overrides", {}).items():
        if not isinstance(rules, dict):
            raise ConfigValidationError(
                f"Budget guardrail safe_category_overrides for '{category}' must be a mapping."
            )
        for complexity, tier in rules.items():
            if tier not in model_tiers:
                raise ConfigValidationError(
                    f"Budget guardrail override '{category}.{complexity}' references unknown model tier '{tier}'."
                )


def _validate_classifier_references(classifier_config: dict[str, Any], model_tiers: set[str]) -> None:
    """Validate cross-config references used by the hybrid classifier."""
    model_tier = classifier_config["stage2"].get("model_tier")
    if model_tier not in model_tiers:
        raise ConfigValidationError(
            f"Classifier stage2 model_tier references unknown model tier '{model_tier}'."
        )
