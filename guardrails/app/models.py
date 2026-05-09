from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User message")


class CloudSafetyRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Prompt to evaluate")
    profile: str = Field(
        default="strict",
        description="Cloud safety profile to use, for example strict or relaxed",
    )


class ChatResponse(BaseModel):
    response: str
    used_backend_data: bool
    model: str
    llm_latency_ms: float
    blocked: bool = False
    guardrail_reason: str | None = None
    guardrails_backend: str | None = None
    input_guardrail_ms: float = 0.0
    output_guardrail_ms: float = 0.0
    trace_id: str | None = None
    traced: bool = False
    latency_ms: float


class CloudSafetyResponse(BaseModel):
    allowed: bool
    action: str
    profile: str
    source: str
    blocked_message: str | None = None
    assessments: list[dict]
    usage: dict | None = None
    latency_ms: float
