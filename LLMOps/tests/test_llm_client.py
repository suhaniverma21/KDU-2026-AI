"""Tests for the LLM client abstraction."""

from __future__ import annotations

import os
import pytest

from src.config_loader import load_all_config
from src.llm_client import (
    BaseProviderAdapter,
    GoogleAIStudioAdapter,
    LLMClient,
    LLMClientError,
    LLMRequest,
    MissingAPIKeyError,
    TransientLLMError,
    generate_response,
)


class FlakyAdapter(BaseProviderAdapter):
    """Adapter that fails once before succeeding."""

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, request: LLMRequest, model_config: dict[str, object]) -> dict[str, object]:
        self.calls += 1
        if self.calls == 1:
            raise TransientLLMError("temporary issue")
        return {
            "response_text": "Recovered response",
            "token_usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            "estimated_cost_usd": 0.001,
        }


class BrokenAdapter(BaseProviderAdapter):
    """Adapter that always fails with a transient error."""

    def generate(self, request: LLMRequest, model_config: dict[str, object]) -> dict[str, object]:
        raise TransientLLMError("still failing")


def test_generate_response_returns_metadata_from_default_client() -> None:
    os.environ["GOOGLE_API_KEY"] = "test-key"

    original_generate = GoogleAIStudioAdapter.generate

    def fake_generate(self, request: LLMRequest, model_config: dict[str, object]) -> dict[str, object]:
        return {
            "response_text": "Gemini mock response",
            "token_usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            "estimated_cost_usd": 0.001,
        }

    GoogleAIStudioAdapter.generate = fake_generate
    try:
        result = generate_response("cheap", "Prompt text", "What are your hours?")
    finally:
        GoogleAIStudioAdapter.generate = original_generate
        os.environ.pop("GOOGLE_API_KEY", None)

    assert result["model_tier"] == "cheap"
    assert result["provider"] == "google_ai_studio"
    assert result["model_name"] == "gemini-2.5-flash-lite"
    assert result["token_usage"]["total_tokens"] >= 1
    assert result["estimated_cost_usd"] >= 0.0


def test_llm_client_generate_supports_prompt_metadata() -> None:
    client = LLMClient(config=load_all_config(), provider_adapters={"google_ai_studio": FlakyAdapter()})

    response = client.generate(
        LLMRequest(
            model_tier="medium",
            prompt="Booking prompt",
            user_query="Can I reschedule my appointment?",
            prompt_id="booking",
            prompt_version="v1",
        )
    )

    assert response.provider == "google_ai_studio"
    assert response.model_name == "gemini-2.5-flash"
    assert response.prompt_id == "booking"
    assert response.prompt_version == "v1"
    assert response.latency_ms >= 0.0


def test_llm_client_retries_transient_failures() -> None:
    config = load_all_config()
    adapter = FlakyAdapter()
    client = LLMClient(config=config, provider_adapters={"google_ai_studio": adapter})

    response = client.generate(
        LLMRequest(model_tier="cheap", prompt="FAQ prompt", user_query="What services do you offer?")
    )

    assert response.response_text == "Recovered response"
    assert response.retries_used == 1
    assert adapter.calls == 2


def test_llm_client_raises_after_retry_limit() -> None:
    config = load_all_config()
    client = LLMClient(config=config, provider_adapters={"google_ai_studio": BrokenAdapter()})

    with pytest.raises(LLMClientError, match="failed after 3 attempts"):
        client.generate(
            LLMRequest(
                model_tier="cheap",
                prompt="FAQ prompt",
                user_query="What services do you offer?",
                max_retries=2,
            )
        )


def test_llm_client_raises_for_unknown_model_tier() -> None:
    client = LLMClient(config=load_all_config())

    with pytest.raises(LLMClientError, match="Unknown model tier"):
        client.generate(LLMRequest(model_tier="unknown", prompt="Prompt", user_query="Hello"))


def test_google_ai_studio_adapter_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    from src import llm_client as llm_client_module
    monkeypatch.setattr(llm_client_module, "load_dotenv_file", lambda: None)
    adapter = GoogleAIStudioAdapter(http_post=lambda *_args, **_kwargs: {})

    with pytest.raises(MissingAPIKeyError, match="Missing Google AI Studio API key"):
        adapter.generate(
            LLMRequest(model_tier="cheap", prompt="Prompt", user_query="Hello"),
            load_all_config()["models"]["models"]["cheap"],
        )


def test_google_ai_studio_adapter_parses_successful_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

    def fake_http_post(_url: str, _payload: dict[str, object], headers: dict[str, str], _timeout: float) -> dict[str, object]:
        assert headers["x-goog-api-key"] == "test-key"
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "Gemini says hello"}]
                    }
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 11,
                "candidatesTokenCount": 7,
                "totalTokenCount": 18,
            },
        }

    adapter = GoogleAIStudioAdapter(http_post=fake_http_post)
    result = adapter.generate(
        LLMRequest(model_tier="cheap", prompt="Prompt", user_query="Hello"),
        load_all_config()["models"]["models"]["cheap"],
    )

    assert result["response_text"] == "Gemini says hello"
    assert result["token_usage"]["total_tokens"] == 18


def test_google_ai_studio_adapter_loads_api_key_from_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    from src import llm_client as llm_client_module

    def fake_load_dotenv_file() -> None:
        os.environ["GOOGLE_API_KEY"] = "dotenv-test-key"

    def fake_http_post(_url: str, _payload: dict[str, object], headers: dict[str, str], _timeout: float) -> dict[str, object]:
        assert headers["x-goog-api-key"] == "dotenv-test-key"
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "Loaded from dotenv"}]
                    }
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 6,
                "candidatesTokenCount": 4,
                "totalTokenCount": 10,
            },
        }

    monkeypatch.setattr(llm_client_module, "load_dotenv_file", fake_load_dotenv_file)
    adapter = GoogleAIStudioAdapter(http_post=fake_http_post)
    result = adapter.generate(
        LLMRequest(model_tier="cheap", prompt="Prompt", user_query="Hello"),
        load_all_config()["models"]["models"]["cheap"],
    )

    assert result["response_text"] == "Loaded from dotenv"
