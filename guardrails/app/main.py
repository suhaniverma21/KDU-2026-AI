from time import perf_counter
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from langsmith import trace as ls_trace
from openai import APIConnectionError, APIError, APIStatusError

from app.cloud_safety import BedrockCloudSafety
from app.guardrails import Phase1Guardrails
from app.llm import VulnerableChatbot
from app.models import ChatRequest, ChatResponse, CloudSafetyRequest, CloudSafetyResponse
from app.observability import get_langsmith_project, is_langsmith_enabled

ROOT_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=ROOT_ENV_PATH, override=True)

app = FastAPI(title="Phase 1 Baseline Chatbot", version="0.1.0")
chatbot = VulnerableChatbot()
guardrails = Phase1Guardrails()
cloud_safety = BedrockCloudSafety()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _run_unguarded_chat(request: ChatRequest, start: float, traced: bool, trace_id: str | None) -> ChatResponse:
    try:
        response, used_backend_data, llm_latency_ms = chatbot.generate_response(
            request.message
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except APIConnectionError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"OpenAI connection error: {exc}",
        ) from exc
    except APIStatusError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except APIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        raise HTTPException(status_code=502, detail=detail) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    latency_ms = round((perf_counter() - start) * 1000, 3)
    return ChatResponse(
        response=response,
        used_backend_data=used_backend_data,
        model=chatbot._load_runtime_config()[1],
        llm_latency_ms=llm_latency_ms,
        blocked=False,
        guardrail_reason=None,
        guardrails_backend=None,
        input_guardrail_ms=0.0,
        output_guardrail_ms=0.0,
        trace_id=trace_id,
        traced=traced,
        latency_ms=latency_ms,
    )


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    start = perf_counter()
    traced = is_langsmith_enabled()

    if not traced:
        return _run_unguarded_chat(request, start, traced=False, trace_id=None)

    with ls_trace(
        "phase1_chat_request",
        run_type="chain",
        inputs={"message": request.message, "endpoint": "/chat"},
        project_name=get_langsmith_project(),
        metadata={"phase": "phase1", "guarded": False},
    ) as rt:
        result = _run_unguarded_chat(request, start, traced=True, trace_id=str(rt.id))
        rt.end(
            outputs={
                "response": result.response,
                "blocked": result.blocked,
                "latency_ms": result.latency_ms,
            },
            metadata={"guardrail_triggered": False},
        )
        return result


def _run_guarded_chat(request: ChatRequest, start: float, traced: bool, trace_id: str | None) -> ChatResponse:
    blocked, reason, input_guardrail_ms = guardrails.inspect_input(request.message)
    if blocked:
        latency_ms = round((perf_counter() - start) * 1000, 3)
        return ChatResponse(
            response="I can help with account-related questions, but I can't follow requests that try to expose hidden or sensitive data.",
            used_backend_data=False,
            model=chatbot._load_runtime_config()[1],
            llm_latency_ms=0.0,
            blocked=True,
            guardrail_reason=reason,
            guardrails_backend=guardrails.backend_name,
            input_guardrail_ms=input_guardrail_ms,
            output_guardrail_ms=0.0,
            trace_id=trace_id,
            traced=traced,
            latency_ms=latency_ms,
        )

    try:
        raw_response, used_backend_data, llm_latency_ms = chatbot.generate_response(
            request.message
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except APIConnectionError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"OpenAI connection error: {exc}",
        ) from exc
    except APIStatusError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except APIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        raise HTTPException(status_code=502, detail=detail) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    safe_response, output_blocked, output_reason, output_guardrail_ms = (
        guardrails.inspect_output(request.message, raw_response)
    )
    latency_ms = round((perf_counter() - start) * 1000, 3)
    return ChatResponse(
        response=safe_response,
        used_backend_data=used_backend_data,
        model=chatbot._load_runtime_config()[1],
        llm_latency_ms=llm_latency_ms,
        blocked=output_blocked,
        guardrail_reason=output_reason,
        guardrails_backend=guardrails.backend_name,
        input_guardrail_ms=input_guardrail_ms,
        output_guardrail_ms=output_guardrail_ms,
        trace_id=trace_id,
        traced=traced,
        latency_ms=latency_ms,
    )


@app.post("/chat-guarded", response_model=ChatResponse)
def chat_guarded(request: ChatRequest) -> ChatResponse:
    start = perf_counter()
    traced = is_langsmith_enabled()

    if not traced:
        return _run_guarded_chat(request, start, traced=False, trace_id=None)

    with ls_trace(
        "phase1_guarded_chat_request",
        run_type="chain",
        inputs={"message": request.message, "endpoint": "/chat-guarded"},
        project_name=get_langsmith_project(),
        metadata={"phase": "phase1", "guarded": True},
    ) as rt:
        result = _run_guarded_chat(request, start, traced=True, trace_id=str(rt.id))
        rt.end(
            outputs={
                "response": result.response,
                "blocked": result.blocked,
                "guardrail_reason": result.guardrail_reason,
                "input_guardrail_ms": result.input_guardrail_ms,
                "output_guardrail_ms": result.output_guardrail_ms,
                "latency_ms": result.latency_ms,
            },
            metadata={
                "guardrail_triggered": bool(result.blocked or result.guardrail_reason),
                "guardrails_backend": result.guardrails_backend,
                "raw_llm_output_present": not result.blocked,
            },
        )
        return result


@app.post("/cloud-safety/evaluate", response_model=CloudSafetyResponse)
def evaluate_cloud_safety(request: CloudSafetyRequest) -> CloudSafetyResponse:
    try:
        result = cloud_safety.evaluate_text(
            text=request.message,
            profile=request.profile,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return CloudSafetyResponse(
        allowed=result["allowed"],
        action=result["action"],
        profile=result["profile"],
        source=result["source"],
        blocked_message=result["blocked_message"],
        assessments=result["assessments"],
        usage=result["usage"],
        latency_ms=result["latency_ms"],
    )
