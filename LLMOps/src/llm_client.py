"""LLM client abstractions for the FixIt LLMOps system."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
import time
from typing import Any, Callable
from urllib import error, request

from .config_loader import load_all_config
from .env_loader import load_dotenv_file


class LLMClientError(RuntimeError):
    """Base exception for LLM client failures."""


class TransientLLMError(LLMClientError):
    """Raised for retryable LLM provider failures."""


class MissingAPIKeyError(LLMClientError):
    """Raised when a required provider API key is not configured."""


@dataclass(frozen=True)
class LLMRequest:
    """Structured request for generating a model response."""

    model_tier: str
    prompt: str
    user_query: str
    prompt_id: str | None = None
    prompt_version: str | None = None
    max_retries: int = 2


@dataclass(frozen=True)
class LLMResponse:
    """Structured response payload returned by the LLM client."""

    response_text: str
    provider: str
    model_name: str
    model_tier: str
    prompt_id: str | None
    prompt_version: str | None
    token_usage: dict[str, int]
    latency_ms: float
    estimated_cost_usd: float
    retries_used: int


class BaseProviderAdapter:
    """Provider-specific adapter interface."""

    def generate(self, request: LLMRequest, model_config: dict[str, Any]) -> dict[str, Any]:
        """Generate a response using the provider's API or local stub."""
        raise NotImplementedError


class GoogleAIStudioAdapter(BaseProviderAdapter):
    """Google AI Studio adapter backed by the Gemini REST API."""

    def __init__(
        self,
        http_post: Callable[[str, dict[str, Any], dict[str, str], float], dict[str, Any]] | None = None,
        api_key_env_vars: tuple[str, ...] = ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
    ) -> None:
        self.http_post = http_post or _http_post_json
        self.api_key_env_vars = api_key_env_vars

    def generate(self, request: LLMRequest, model_config: dict[str, Any]) -> dict[str, Any]:
        api_key = _resolve_api_key(self.api_key_env_vars)
        model_name = model_config["model_name"]
        timeout_seconds = float(model_config.get("timeout_seconds", 30))
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": _build_combined_prompt(
                                system_prompt=request.prompt,
                                user_query=request.user_query,
                            )
                        }
                    ],
                }
            ]
        }
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        }

        provider_result = self.http_post(url, payload, headers, timeout_seconds)
        response_text = _extract_response_text(provider_result)
        token_usage = _extract_token_usage(provider_result)
        estimated_cost = _estimate_cost(
            model_config,
            token_usage["input_tokens"],
            token_usage["output_tokens"],
        )

        return {
            "response_text": response_text,
            "token_usage": token_usage,
            "estimated_cost_usd": estimated_cost,
        }


class LLMClient:
    """Provider-agnostic client that routes requests by logical model tier."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        provider_adapters: dict[str, BaseProviderAdapter] | None = None,
    ) -> None:
        self.config = config or load_all_config()
        self.models = self.config["models"]["models"]
        self.provider_adapters = provider_adapters or {"google_ai_studio": GoogleAIStudioAdapter()}

    def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate a response with retry handling for transient provider failures."""
        model_config = self.models.get(request.model_tier)
        if model_config is None:
            raise LLMClientError(f"Unknown model tier: {request.model_tier}")
        if not model_config.get("enabled", False):
            raise LLMClientError(f"Model tier '{request.model_tier}' is disabled.")

        provider_name = model_config["provider"]
        adapter = self.provider_adapters.get(provider_name)
        if adapter is None:
            raise LLMClientError(f"No provider adapter registered for '{provider_name}'.")

        start_time = time.perf_counter()
        retries_used = 0
        last_error: Exception | None = None

        for attempt in range(request.max_retries + 1):
            try:
                provider_result = adapter.generate(request, model_config)
                latency_ms = (time.perf_counter() - start_time) * 1000
                return LLMResponse(
                    response_text=provider_result["response_text"],
                    provider=provider_name,
                    model_name=model_config["model_name"],
                    model_tier=request.model_tier,
                    prompt_id=request.prompt_id,
                    prompt_version=request.prompt_version,
                    token_usage=provider_result["token_usage"],
                    latency_ms=round(latency_ms, 2),
                    estimated_cost_usd=provider_result["estimated_cost_usd"],
                    retries_used=retries_used,
                )
            except MissingAPIKeyError:
                raise
            except TransientLLMError as exc:
                last_error = exc
                retries_used = attempt + 1
                if attempt >= request.max_retries:
                    break
            except Exception as exc:
                raise LLMClientError(f"Provider call failed: {exc}") from exc

        raise LLMClientError(
            f"Provider call failed after {request.max_retries + 1} attempts: {last_error}"
        ) from last_error


def generate_response(model_tier: str, prompt: str, user_query: str) -> dict[str, Any]:
    """Backward-compatible helper that uses the default LLM client."""
    client = LLMClient()
    response = client.generate(
        LLMRequest(
            model_tier=model_tier,
            prompt=prompt,
            user_query=user_query,
        )
    )
    return asdict(response)


def _resolve_api_key(api_key_env_vars: tuple[str, ...]) -> str:
    """Resolve a provider API key from supported environment variables."""
    load_dotenv_file()
    for env_var in api_key_env_vars:
        api_key = os.getenv(env_var)
        if api_key:
            return api_key
    raise MissingAPIKeyError(
        "Missing Google AI Studio API key. Set GOOGLE_API_KEY or GEMINI_API_KEY."
    )


def _build_combined_prompt(*, system_prompt: str, user_query: str) -> str:
    """Build a single text prompt for Gemini content generation."""
    return f"{system_prompt}\n\nCustomer query:\n{user_query}"


def _extract_response_text(provider_result: dict[str, Any]) -> str:
    """Extract generated text from a Gemini generateContent response."""
    candidates = provider_result.get("candidates", [])
    for candidate in candidates:
        parts = candidate.get("content", {}).get("parts", [])
        text_parts = [part.get("text", "") for part in parts if part.get("text")]
        if text_parts:
            return "\n".join(text_parts).strip()
    raise LLMClientError("Google AI Studio response did not include generated text.")


def _extract_token_usage(provider_result: dict[str, Any]) -> dict[str, int]:
    """Extract usage metadata from a Gemini generateContent response."""
    usage = provider_result.get("usageMetadata", {})
    input_tokens = int(usage.get("promptTokenCount", 0))
    output_tokens = int(usage.get("candidatesTokenCount", 0))
    total_tokens = int(usage.get("totalTokenCount", input_tokens + output_tokens))
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def _http_post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout_seconds: float,
) -> dict[str, Any]:
    """Send a JSON POST request and return the parsed response body."""
    encoded_payload = json.dumps(payload).encode("utf-8")
    http_request = request.Request(url, data=encoded_payload, headers=headers, method="POST")

    try:
        with request.urlopen(http_request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        if exc.code in {408, 429, 500, 502, 503, 504}:
            raise TransientLLMError(
                f"Google AI Studio request failed with HTTP {exc.code}: {error_body}"
            ) from exc
        raise LLMClientError(
            f"Google AI Studio request failed with HTTP {exc.code}: {error_body}"
        ) from exc
    except error.URLError as exc:
        raise TransientLLMError(f"Google AI Studio network error: {exc}") from exc


def _estimate_cost(model_config: dict[str, Any], input_tokens: int, output_tokens: int) -> float:
    """Estimate cost from model pricing metadata."""
    input_rate = float(model_config.get("input_cost_per_1k_tokens_usd", 0.0))
    output_rate = float(model_config.get("output_cost_per_1k_tokens_usd", 0.0))
    cost = (input_tokens / 1000 * input_rate) + (output_tokens / 1000 * output_rate)
    return round(cost, 6)
