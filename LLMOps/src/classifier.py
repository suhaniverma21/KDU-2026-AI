"""Hybrid query classification utilities for the FixIt LLMOps system."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import re
from typing import Any

from .config_loader import load_all_config
from .fallback_handler import resolve_fallback
from .llm_client import LLMClient, LLMClientError, LLMRequest


@dataclass(frozen=True)
class ClassificationResult:
    """Structured output for query classification."""

    query: str
    category: str
    complexity: str
    confidence: float
    reasoning: str
    matched_rules: list[str]
    classifier_source: str
    stage2_triggered: bool
    direct_accept: bool
    resolved: bool
    competing_categories: list[str]
    classification_cost_usd: float
    classifier_model_tier: str | None
    fallback_events: list[dict[str, Any]]


@dataclass(frozen=True)
class Stage1Result:
    """Output of the lightweight deterministic pre-classifier."""

    query: str
    category: str
    complexity: str
    confidence: float
    reasoning: str
    matched_rules: list[str]
    competing_categories: list[str]
    direct_accept: bool
    should_escalate: bool


class BaseClassifier:
    """Interface for pluggable classifiers."""

    def classify(self, query: str) -> ClassificationResult:
        """Classify the provided query."""
        raise NotImplementedError


class RulePreClassifier:
    """Deterministic pre-classifier used only for obvious cases."""

    CATEGORY_RULES = {
        "FAQ": (
            "hours",
            "open",
            "close",
            "available",
            "services",
            "service area",
            "price",
            "pricing",
            "cost",
            "quote",
            "when are you open",
            "what services",
        ),
        "booking": (
            "book",
            "booking",
            "schedule",
            "reschedule",
            "appointment",
            "cancel",
            "change my appointment",
            "move my appointment",
            "visit",
            "confirm my booking",
        ),
        "complaint": (
            "refund",
            "complaint",
            "issue",
            "problem",
            "didn't show up",
            "did not show up",
            "late",
            "damaged",
            "bad service",
            "unhappy",
            "charge dispute",
            "angry",
            "missed appointment",
        ),
    }

    HIGH_COMPLEXITY_RULES = (
        "refund",
        "complaint",
        "escalate",
        "urgent",
        "asap",
        "damaged",
        "didn't show up",
        "did not show up",
        "charge dispute",
        "unsafe",
        "missed appointment",
    )
    MEDIUM_COMPLEXITY_RULES = (
        "reschedule",
        "cancel",
        "change",
        "appointment",
        "booking",
        "schedule",
        "quote",
        "confirm",
    )

    def __init__(self, classifier_config: dict[str, Any]) -> None:
        self.classifier_config = classifier_config
        self.stage1_config = classifier_config["stage1"]

    def classify(self, query: str) -> Stage1Result:
        """Run the cheap deterministic pre-classifier."""
        normalized_query = _normalize_text(query)
        category_scores, matched_rules = self._score_categories(normalized_query)
        category, confidence, competing_categories, margin = self._select_category(category_scores, normalized_query)
        complexity = self._classify_complexity(normalized_query)
        direct_accept = self._should_accept_directly(
            highest_score=max(category_scores.values()),
            confidence=confidence,
            margin=margin,
        )
        should_escalate = not direct_accept
        reasoning = self._build_reasoning(
            category=category,
            complexity=complexity,
            confidence=confidence,
            matched_rules=matched_rules,
            competing_categories=competing_categories,
            direct_accept=direct_accept,
        )

        return Stage1Result(
            query=query,
            category=category,
            complexity=complexity,
            confidence=confidence,
            reasoning=reasoning,
            matched_rules=matched_rules,
            competing_categories=competing_categories,
            direct_accept=direct_accept,
            should_escalate=should_escalate,
        )

    def _score_categories(self, normalized_query: str) -> tuple[dict[str, int], list[str]]:
        scores = {category: 0 for category in self.CATEGORY_RULES}
        matched_rules: list[str] = []

        for category, rules in self.CATEGORY_RULES.items():
            for rule in rules:
                if rule in normalized_query:
                    scores[category] += 1
                    matched_rules.append(f"{category}:{rule}")

        return scores, matched_rules

    def _select_category(
        self,
        scores: dict[str, int],
        normalized_query: str,
    ) -> tuple[str, float, list[str], int]:
        highest_score = max(scores.values())
        if highest_score == 0:
            return "FAQ", 0.2 if normalized_query else 0.0, [], 0

        sorted_scores = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        highest_categories = [category for category, score in scores.items() if score == highest_score]
        second_best_score = sorted_scores[1][1] if len(sorted_scores) > 1 else 0
        margin = highest_score - second_best_score

        if len(highest_categories) > 1:
            return "FAQ", 0.45, highest_categories, 0

        confidence = min(0.45 + highest_score * 0.15 + max(margin, 0) * 0.1, 0.98)
        return sorted_scores[0][0], confidence, [], margin

    def _classify_complexity(self, normalized_query: str) -> str:
        if any(rule in normalized_query for rule in self.HIGH_COMPLEXITY_RULES):
            return "high"
        if any(rule in normalized_query for rule in self.MEDIUM_COMPLEXITY_RULES):
            return "medium"
        return "low"

    def _should_accept_directly(self, *, highest_score: int, confidence: float, margin: int) -> bool:
        return (
            highest_score >= int(self.stage1_config["minimum_rule_hits_for_direct_accept"])
            and margin >= int(self.stage1_config["minimum_margin_for_direct_accept"])
            and confidence >= float(self.stage1_config["direct_accept_confidence"])
        )

    def _build_reasoning(
        self,
        *,
        category: str,
        complexity: str,
        confidence: float,
        matched_rules: list[str],
        competing_categories: list[str],
        direct_accept: bool,
    ) -> str:
        if not matched_rules:
            return "Stage 1 found no strong lexical evidence; escalation recommended."
        if competing_categories:
            return f"Stage 1 found competing categories {competing_categories}; escalation recommended."
        trust_text = "trusted directly" if direct_accept else "not trusted directly"
        return (
            f"Stage 1 matched rules {matched_rules}; predicted '{category}' / '{complexity}' "
            f"with confidence {confidence:.2f} and result was {trust_text}."
        )


class HybridClassifier(BaseClassifier):
    """Cheap-first classifier with optional LLM escalation for uncertain cases."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        self.config = config or load_all_config()
        self.classifier_config = self.config["classifier"]["classifier"]
        self.stage1_config = self.classifier_config["stage1"]
        self.stage2_config = self.classifier_config["stage2"]
        self.fallback_config = self.classifier_config["fallback"]
        self.pre_classifier = RulePreClassifier(self.classifier_config)
        self.llm_client = llm_client or LLMClient(config=self.config)

    def classify(self, query: str) -> ClassificationResult:
        """Run the hybrid classification flow."""
        stage1_result = self.pre_classifier.classify(query)
        fallback_events: list[dict[str, Any]] = []

        if stage1_result.direct_accept:
            return ClassificationResult(
                query=query,
                category=stage1_result.category,
                complexity=stage1_result.complexity,
                confidence=stage1_result.confidence,
                reasoning=stage1_result.reasoning,
                matched_rules=stage1_result.matched_rules,
                classifier_source="stage1_rules",
                stage2_triggered=False,
                direct_accept=True,
                resolved=True,
                competing_categories=stage1_result.competing_categories,
                classification_cost_usd=0.0,
                classifier_model_tier=None,
                fallback_events=fallback_events,
            )

        fallback_events.append(
            resolve_fallback(
                "low_confidence_rule_classification",
                config=self.config,
                classification={"confidence": stage1_result.confidence},
                confidence_threshold=float(self.stage1_config["escalation_confidence_threshold"]),
            )
        )

        if not self.stage2_config["enabled"]:
            return self._build_unresolved_result(
                query=query,
                stage1_result=stage1_result,
                fallback_events=fallback_events,
                reason="Stage 2 classifier is disabled; unresolved classification routed safely.",
            )

        try:
            stage2_result, stage2_cost, model_tier = self._classify_with_llm(query)
            return ClassificationResult(
                query=query,
                category=stage2_result["category"],
                complexity=stage2_result["complexity"],
                confidence=float(stage2_result["confidence"]),
                reasoning=str(stage2_result["reasoning"]),
                matched_rules=stage1_result.matched_rules,
                classifier_source=str(stage2_result.get("classifier_source", "stage2_llm")),
                stage2_triggered=True,
                direct_accept=False,
                resolved=True,
                competing_categories=stage1_result.competing_categories,
                classification_cost_usd=stage2_cost,
                classifier_model_tier=model_tier,
                fallback_events=fallback_events,
            )
        except LLMClientError as exc:
            fallback_events.append(
                resolve_fallback(
                    "secondary_classifier_failure",
                    config=self.config,
                    error_message=str(exc),
                )
            )
            return self._build_unresolved_result(
                query=query,
                stage1_result=stage1_result,
                fallback_events=fallback_events,
                reason=f"Stage 2 classifier failed and classification remains unresolved: {exc}",
            )

    def _classify_with_llm(self, query: str) -> tuple[dict[str, Any], float, str]:
        model_tier = str(self.stage2_config["model_tier"])
        llm_prompt = self._build_stage2_prompt()
        response = self.llm_client.generate(
            LLMRequest(
                model_tier=model_tier,
                prompt=llm_prompt,
                user_query=query,
                prompt_id="hybrid_classifier",
                prompt_version="v1",
                max_retries=int(self.stage2_config["max_retries"]),
            )
        )
        parsed = _parse_json_response(response.response_text)
        category = parsed.get("category")
        complexity = parsed.get("complexity")

        allowed_categories = set(self.classifier_config["taxonomy"]["categories"])
        allowed_complexities = set(self.classifier_config["taxonomy"]["complexity_levels"])
        if category not in allowed_categories or complexity not in allowed_complexities:
            raise LLMClientError("Stage 2 classifier returned an invalid category or complexity.")

        return (
            {
                "category": str(category),
                "complexity": str(complexity),
                "confidence": float(parsed.get("confidence", 0.75)),
                "reasoning": str(parsed.get("reasoning", "Stage 2 LLM classification.")),
                "classifier_source": str(parsed.get("classifier_source", "stage2_llm")),
            },
            float(response.estimated_cost_usd),
            model_tier,
        )

    def _build_stage2_prompt(self) -> str:
        return (
            "You are a support query classifier for FixIt.\n"
            "Classify the customer query into exactly one category and one complexity.\n"
            "Allowed categories: FAQ, booking, complaint.\n"
            "Allowed complexity: low, medium, high.\n"
            "Return JSON only with keys: category, complexity, confidence, reasoning, classifier_source.\n"
            'Set classifier_source to "stage2_llm".\n'
            "Do not invent extra fields."
        )

    def _build_unresolved_result(
        self,
        *,
        query: str,
        stage1_result: Stage1Result,
        fallback_events: list[dict[str, Any]],
        reason: str,
    ) -> ClassificationResult:
        fallback_events.append(
            resolve_fallback(
                "unresolved_classification",
                config=self.config,
                error_message=reason,
            )
        )
        return ClassificationResult(
            query=query,
            category=stage1_result.category,
            complexity=str(self.fallback_config["unresolved_complexity"]),
            confidence=float(self.fallback_config["unresolved_confidence"]),
            reasoning=reason,
            matched_rules=stage1_result.matched_rules,
            classifier_source="classifier_fallback",
            stage2_triggered=bool(self.stage2_config["enabled"]),
            direct_accept=False,
            resolved=False,
            competing_categories=stage1_result.competing_categories,
            classification_cost_usd=0.0,
            classifier_model_tier=None,
            fallback_events=fallback_events,
        )


def classify_query(
    query: str,
    classifier: BaseClassifier | None = None,
    *,
    config: dict[str, Any] | None = None,
    llm_client: LLMClient | None = None,
) -> dict[str, Any]:
    """Classify a query using the provided classifier or the default hybrid classifier."""
    active_classifier = classifier or HybridClassifier(config=config, llm_client=llm_client)
    return asdict(active_classifier.classify(query))


def _normalize_text(text: str) -> str:
    """Normalize customer query text for simple rule matching."""
    lowered = text.strip().lower()
    return re.sub(r"\s+", " ", lowered)


def _parse_json_response(response_text: str) -> dict[str, Any]:
    """Parse the first JSON object from a model response."""
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        start = response_text.find("{")
        end = response_text.rfind("}")
        if start == -1 or end == -1 or start >= end:
            raise LLMClientError("Stage 2 classifier returned invalid JSON.")
        try:
            return json.loads(response_text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LLMClientError("Stage 2 classifier returned invalid JSON.") from exc
