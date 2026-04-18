"""Main orchestration entry point for the FixIt LLMOps system."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .classifier import BaseClassifier, classify_query
from .config_loader import load_all_config
from .cost_tracker import CostTracker
from .fallback_handler import SAFE_SUPPORT_RESPONSE, build_safe_fallback, resolve_fallback
from .llm_client import LLMClient, LLMClientError, LLMRequest, LLMResponse
from .observability import RequestTrace, build_request_log_entry, create_request_trace, emit_structured_log
from .prompt_manager import PROMPTS_DIR, PromptNotFoundError, load_prompt
from .router import route_query

MetadataDict = dict[str, Any]


def handle_query(
    query: str,
    *,
    config: dict[str, Any] | None = None,
    classifier: BaseClassifier | None = None,
    llm_client: LLMClient | None = None,
    cost_tracker: CostTracker | None = None,
    prompts_dir: str | Path = PROMPTS_DIR,
    confidence_threshold: float = 0.6,
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    """Run the end-to-end FixIt support flow for a customer query."""
    normalized_query = _validate_query_input(query)
    active_config = config or load_all_config()
    tracker = cost_tracker or CostTracker(config=active_config)
    client = llm_client or LLMClient(config=active_config)
    feature_flags = active_config["feature_flags"]["feature_flags"]
    classifier_config = active_config["classifier"]["classifier"]
    request_trace = create_request_trace()
    active_confidence_threshold = float(
        classifier_config["stage1"]["escalation_confidence_threshold"]
        if confidence_threshold == 0.6
        else confidence_threshold
    )

    classification = classify_query(
        normalized_query,
        classifier=classifier,
        config=active_config,
        llm_client=client,
    )
    classification_cost = float(classification.get("classification_cost_usd", 0.0))
    if classification_cost > 0:
        tracker.add_classifier_cost(classification_cost)
    budget_status = tracker.get_budget_status()
    route = route_query(
        classification,
        config=active_config,
        budget_status=budget_status,
        confidence_threshold=active_confidence_threshold,
    )

    fallback_events: list[dict[str, Any]] = list(classification.get("fallback_events", []))
    _collect_pre_response_fallbacks(
        fallback_events=fallback_events,
        feature_flags=feature_flags,
        classification=classification,
        route=route,
        config=active_config,
        budget_status=budget_status,
        confidence_threshold=active_confidence_threshold,
    )

    prompt = _resolve_prompt_with_fallback(
        category=classification["category"],
        config=active_config,
        prompts_dir=prompts_dir,
        fallback_events=fallback_events,
    )

    response_payload = _generate_with_fallback(
        query=normalized_query,
        route=route,
        prompt=prompt,
        client=client,
        config=active_config,
        fallback_events=fallback_events,
    )

    request_cost = float(response_payload["estimated_cost_usd"])
    monthly_spend = tracker.add_request_cost(request_cost)
    monthly_summary = tracker.get_monthly_summary()

    metadata = _build_response_metadata(
        query=normalized_query,
        request_trace=request_trace,
        classification=classification,
        budget_status=budget_status,
        route=route,
        prompt=prompt,
        response_payload=response_payload,
        classification_cost=classification_cost,
        request_cost=request_cost,
        monthly_spend=monthly_spend,
        monthly_summary=monthly_summary,
        fallback_events=fallback_events,
    )
    result = {
        "response_text": response_payload["response_text"],
        "metadata": metadata,
    }

    if feature_flags.get("enable_request_logging", False):
        emit_structured_log(
            build_request_log_entry(
                request_trace=request_trace,
                query=normalized_query,
                metadata=metadata,
            ),
            logger=logger,
        )

    return result


def analyze_query(
    query: str,
    *,
    config: dict[str, Any] | None = None,
    classifier: BaseClassifier | None = None,
    llm_client: LLMClient | None = None,
    cost_tracker: CostTracker | None = None,
    confidence_threshold: float = 0.6,
    disable_stage2_classifier: bool = False,
) -> dict[str, Any]:
    """Classify and route a query without generating a live LLM response."""
    normalized_query = _validate_query_input(query)
    active_config = config or load_all_config()
    analysis_config = active_config
    if disable_stage2_classifier:
        analysis_config = _with_stage2_classifier_disabled(active_config)

    tracker = cost_tracker or CostTracker(config=analysis_config)
    client = llm_client or LLMClient(config=analysis_config)
    feature_flags = analysis_config["feature_flags"]["feature_flags"]
    classifier_config = analysis_config["classifier"]["classifier"]
    request_trace = create_request_trace()
    active_confidence_threshold = float(
        classifier_config["stage1"]["escalation_confidence_threshold"]
        if confidence_threshold == 0.6
        else confidence_threshold
    )

    classification = classify_query(
        normalized_query,
        classifier=classifier,
        config=analysis_config,
        llm_client=client,
    )
    classification_cost = float(classification.get("classification_cost_usd", 0.0))
    if classification_cost > 0:
        tracker.add_classifier_cost(classification_cost)
    budget_status = tracker.get_budget_status()
    route = route_query(
        classification,
        config=analysis_config,
        budget_status=budget_status,
        confidence_threshold=active_confidence_threshold,
    )

    fallback_events: list[dict[str, Any]] = list(classification.get("fallback_events", []))
    _collect_pre_response_fallbacks(
        fallback_events=fallback_events,
        feature_flags=feature_flags,
        classification=classification,
        route=route,
        config=analysis_config,
        budget_status=budget_status,
        confidence_threshold=active_confidence_threshold,
    )

    monthly_summary = tracker.get_monthly_summary()
    metadata = {
        "request_id": request_trace.request_id,
        "started_at_utc": request_trace.started_at_utc,
        "query": normalized_query,
        "classification": classification,
        "budget_status_before_request": budget_status,
        "route": route,
        "cost": {
            "classification_cost_usd": classification_cost,
            "response_generation_cost_usd": 0.0,
            "request_cost_usd": classification_cost,
            "monthly_spend_usd": monthly_summary["monthly_spend_usd"],
            "budget_status_after_request": monthly_summary["budget_status"],
            "remaining_budget_usd": monthly_summary["remaining_budget_usd"],
            "cost_breakdown_usd": monthly_summary["cost_breakdown_usd"],
            "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        },
        "fallback": {
            "applied": bool(fallback_events),
            "events": fallback_events,
        },
        "llm_generation_skipped": True,
        "skip_reason": (
            "Live LLM generation was skipped by CLI flag."
            if not disable_stage2_classifier
            else "All live LLM calls were skipped by CLI flag, including the secondary classifier."
        ),
    }
    return {
        "response_text": "LLM generation was skipped.",
        "metadata": metadata,
    }


def _collect_pre_response_fallbacks(
    *,
    fallback_events: list[dict[str, Any]],
    feature_flags: dict[str, Any],
    classification: dict[str, Any],
    route: dict[str, Any],
    config: dict[str, Any],
    budget_status: str,
    confidence_threshold: float,
) -> None:
    """Collect fallback events that can be determined before generation starts."""
    if (
        feature_flags.get("enable_fallback", False)
        and classification["confidence"] < confidence_threshold
        and classification.get("resolved", True)
    ):
        fallback_events.append(
            resolve_fallback(
                "low_confidence",
                config=config,
                classification=classification,
                route=route,
                confidence_threshold=confidence_threshold,
            )
        )

    if budget_status == "hard_limit":
        fallback_events.append(
            resolve_fallback(
                "budget_limit_exceeded",
                config=config,
                route=route,
            )
        )


def _resolve_prompt_with_fallback(
    *,
    category: str,
    config: dict[str, Any],
    prompts_dir: str | Path,
    fallback_events: list[dict[str, Any]],
) -> MetadataDict:
    """Load the routed prompt, falling back to the configured default prompt if needed."""
    try:
        return load_prompt(category, config=config, prompts_dir=prompts_dir)
    except PromptNotFoundError as exc:
        fallback = resolve_fallback(
            "missing_prompt",
            config=config,
            error_message=str(exc),
        )
        fallback_events.append(fallback)
        prompt_id = fallback["prompt_id"] or config["prompts"]["default_prompt"]["prompt_id"]
        prompt_version = fallback["prompt_version"] or config["prompts"]["default_prompt"]["version"]
        try:
            prompt = load_prompt(
                prompt_id,
                version=prompt_version,
                config=config,
                prompts_dir=prompts_dir,
            )
            return prompt | {"fallback_applied": True}
        except PromptNotFoundError:
            return _build_safe_prompt_payload(prompt_id=prompt_id, prompt_version=prompt_version)


def _generate_with_fallback(
    *,
    query: str,
    route: dict[str, Any],
    prompt: dict[str, Any],
    client: LLMClient,
    config: dict[str, Any],
    fallback_events: list[dict[str, Any]],
) -> MetadataDict:
    """Generate a response, applying model fallback on provider failure when possible."""
    try:
        response = client.generate(_build_llm_request(model_tier=route["selected_tier"], prompt=prompt, query=query))
        return _serialize_llm_response(response)
    except LLMClientError as exc:
        fallback = resolve_fallback(
            "model_api_failure",
            config=config,
            route=route,
            prompt=prompt,
            error_message=str(exc),
        )
        fallback_events.append(fallback)
        fallback_tier = fallback["selected_tier"]

        if fallback_tier and fallback_tier != route["selected_tier"]:
            try:
                retry_response = client.generate(
                    _build_llm_request(model_tier=fallback_tier, prompt=prompt, query=query)
                )
                return _serialize_llm_response(retry_response)
            except LLMClientError as retry_exc:
                fallback_events.append(build_safe_fallback(f"Fallback model generation failed: {retry_exc}"))

        return _build_safe_model_response(fallback_tier=fallback_tier)


def _build_llm_request(*, model_tier: str, prompt: dict[str, Any], query: str) -> LLMRequest:
    """Build the canonical LLM request object for a prompt and customer query."""
    return LLMRequest(
        model_tier=model_tier,
        prompt=prompt["content"],
        user_query=query,
        prompt_id=prompt["prompt_id"],
        prompt_version=prompt["version"],
    )


def _serialize_llm_response(response: LLMResponse) -> MetadataDict:
    """Normalize client responses into the metadata shape used by the main flow."""
    return {
        "response_text": response.response_text,
        "provider": response.provider,
        "model_name": response.model_name,
        "model_tier": response.model_tier,
        "latency_ms": response.latency_ms,
        "retries_used": response.retries_used,
        "estimated_cost_usd": response.estimated_cost_usd,
        "token_usage": response.token_usage,
    }


def _build_safe_prompt_payload(*, prompt_id: str, prompt_version: str) -> MetadataDict:
    """Return a minimal prompt payload when prompt resolution cannot recover from failure."""
    return {
        "prompt_id": prompt_id,
        "category": "FAQ",
        "version": prompt_version,
        "path": "",
        "content": SAFE_SUPPORT_RESPONSE,
        "intended_use": "Safe fallback support response.",
        "fallback_applied": True,
    }


def _build_safe_model_response(*, fallback_tier: str | None) -> MetadataDict:
    """Return a deterministic safe response payload when model generation cannot recover."""
    return {
        "response_text": SAFE_SUPPORT_RESPONSE,
        "provider": "system",
        "model_name": "safe_fallback",
        "model_tier": fallback_tier or "safe_fallback",
        "latency_ms": 0.0,
        "retries_used": 0,
        "estimated_cost_usd": 0.0,
        "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
    }


def _build_response_metadata(
    *,
    query: str,
    request_trace: RequestTrace,
    classification: dict[str, Any],
    budget_status: str,
    route: dict[str, Any],
    prompt: dict[str, Any],
    response_payload: dict[str, Any],
    classification_cost: float,
    request_cost: float,
    monthly_spend: float,
    monthly_summary: dict[str, Any],
    fallback_events: list[dict[str, Any]],
) -> MetadataDict:
    """Build the stable metadata envelope returned by the main flow."""
    return {
        "request_id": request_trace.request_id,
        "started_at_utc": request_trace.started_at_utc,
        "query": query,
        "classification": classification,
        "budget_status_before_request": budget_status,
        "route": route,
        "prompt": {
            "prompt_id": prompt["prompt_id"],
            "category": prompt["category"],
            "version": prompt["version"],
            "fallback_applied": prompt["fallback_applied"],
            "path": prompt["path"],
        },
        "model": {
            "tier": response_payload["model_tier"],
            "provider": response_payload["provider"],
            "name": response_payload["model_name"],
            "latency_ms": response_payload["latency_ms"],
            "retries_used": response_payload["retries_used"],
        },
        "cost": {
            "classification_cost_usd": classification_cost,
            "response_generation_cost_usd": request_cost,
            "request_cost_usd": round(classification_cost + request_cost, 6),
            "monthly_spend_usd": monthly_spend,
            "budget_status_after_request": monthly_summary["budget_status"],
            "remaining_budget_usd": monthly_summary["remaining_budget_usd"],
            "cost_breakdown_usd": monthly_summary["cost_breakdown_usd"],
            "token_usage": response_payload["token_usage"],
        },
        "fallback": {
            "applied": bool(fallback_events),
            "events": fallback_events,
        },
    }


def _validate_query_input(query: str) -> str:
    """Validate and normalize a user-supplied query string."""
    if not isinstance(query, str):
        raise TypeError("query must be a string.")

    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("query cannot be empty.")
    return normalized_query


def _with_stage2_classifier_disabled(config: dict[str, Any]) -> dict[str, Any]:
    """Return a config copy with the hybrid classifier's stage 2 disabled."""
    classifier_config = config["classifier"]["classifier"]
    updated_classifier = {
        **classifier_config,
        "stage2": {**classifier_config["stage2"], "enabled": False},
    }
    return {
        **config,
        "classifier": {
            **config["classifier"],
            "classifier": updated_classifier,
        },
    }


if __name__ == "__main__":
    sample_result = handle_query("What are your hours?")
    print(sample_result["response_text"])
