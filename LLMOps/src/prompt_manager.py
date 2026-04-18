"""Prompt loading and version management for the FixIt LLMOps system."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .config_loader import load_all_config

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


@dataclass(frozen=True)
class PromptResolution:
    """Resolved prompt content and metadata."""

    prompt_id: str
    category: str
    version: str
    file_name: str
    path: str
    content: str
    intended_use: str
    fallback_applied: bool


class PromptNotFoundError(FileNotFoundError):
    """Raised when a prompt or prompt file cannot be resolved."""


def load_prompt_registry(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the prompt registry section from configuration."""
    active_config = config or load_all_config()
    return active_config["prompts"]


def load_prompt(
    prompt_name: str,
    version: str | None = None,
    config: dict[str, Any] | None = None,
    prompts_dir: str | Path = PROMPTS_DIR,
) -> dict[str, Any]:
    """Load a prompt by category or prompt id, applying version fallback when needed."""
    registry = load_prompt_registry(config)
    prompt_entry = _find_prompt_entry(prompt_name, registry["prompts"])
    resolved_version = version or _get_current_version(prompt_entry)
    fallback_version = prompt_entry["fallback_version"]

    prompt_version_config = prompt_entry.get("versions", {}).get(resolved_version)
    fallback_applied = False

    if prompt_version_config is None:
        prompt_version_config = prompt_entry.get("versions", {}).get(fallback_version)
        resolved_version = fallback_version
        fallback_applied = True

    if prompt_version_config is None:
        default_prompt = registry.get("default_prompt", {})
        default_entry = _find_prompt_entry(default_prompt.get("prompt_id", "faq"), registry["prompts"])
        default_version = default_prompt.get("version", default_entry["fallback_version"])
        prompt_version_config = default_entry.get("versions", {}).get(default_version)
        prompt_entry = default_entry
        resolved_version = default_version
        fallback_applied = True

    if prompt_version_config is None:
        raise PromptNotFoundError(f"Unable to resolve prompt for '{prompt_name}'.")

    file_name = prompt_version_config["file"]
    path = Path(prompts_dir) / file_name

    if not path.exists():
        if resolved_version != fallback_version:
            return load_prompt(
                prompt_entry["prompt_id"],
                version=fallback_version,
                config=config,
                prompts_dir=prompts_dir,
            ) | {"fallback_applied": True}
        raise PromptNotFoundError(f"Prompt file not found: {path}")

    return asdict(
        PromptResolution(
            prompt_id=prompt_entry["prompt_id"],
            category=prompt_entry["category"],
            version=resolved_version,
            file_name=file_name,
            path=str(path),
            content=path.read_text(encoding="utf-8"),
            intended_use=prompt_entry.get("intended_use", ""),
            fallback_applied=fallback_applied,
        )
    )


def _find_prompt_entry(prompt_name: str, prompt_registry: dict[str, Any]) -> dict[str, Any]:
    """Resolve a prompt registry entry by category name or prompt id."""
    if prompt_name in prompt_registry:
        return prompt_registry[prompt_name]

    for prompt_entry in prompt_registry.values():
        if prompt_entry.get("prompt_id") == prompt_name:
            return prompt_entry

    raise PromptNotFoundError(f"Prompt '{prompt_name}' is not defined in the prompt registry.")


def _get_current_version(prompt_entry: dict[str, Any]) -> str:
    """Return the configured current version for a prompt entry."""
    current_version = prompt_entry.get("current_version", prompt_entry.get("active_version"))
    if not current_version:
        raise PromptNotFoundError(
            f"Prompt '{prompt_entry.get('prompt_id', 'unknown')}' does not define a current version."
        )
    return current_version
