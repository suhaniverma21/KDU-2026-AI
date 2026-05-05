from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class DemoLoginRequest(BaseModel):
    user_id: str


class SessionBootstrapRequest(BaseModel):
    thread_id: str


class ThreadSummary(BaseModel):
    id: str
    title: str
    mode: Literal["ai", "human"] = "ai"


class DemoLoginResponse(BaseModel):
    user_id: str
    thread_ids: list[str]
    default_thread_id: str


class SessionResponse(BaseModel):
    client_secret: str
    expires_at: int
    thread_id: str
    session_id: str


class WidgetActionSchema(BaseModel):
    id: str
    label: str
    style: Literal["primary", "secondary"] = "primary"


class WidgetSchema(BaseModel):
    id: str
    type: str
    data: dict[str, Any]
    actions: list[WidgetActionSchema] = Field(default_factory=list)
    expires_at: int
    state: Literal["idle", "loading", "success", "error"] = "idle"
    version: int = 1


class ThreadRecord(BaseModel):
    id: str
    user_id: str
    title: str
    created_at: int
    updated_at: int
    mode: Literal["ai", "human"] = "ai"
    metadata: dict[str, Any] = Field(default_factory=dict)


class MessageRecord(BaseModel):
    id: str
    thread_id: str
    role: Literal["user", "assistant", "tool"]
    content: str | dict[str, Any]
    timestamp: int
    status: Literal["delivered", "streaming", "failed", "cancelled"]
    hidden: bool = False


class AuthContext(BaseModel):
    user_id: str
    thread_id: str
    issued_at: int
    expires_at: int


class ChatMessageRequest(BaseModel):
    thread_id: str
    client_secret: str
    text: str


class CancelStreamRequest(BaseModel):
    thread_id: str
    stream_id: str


class WidgetActionRequest(BaseModel):
    thread_id: str
    client_secret: str
    widget_id: str
    action_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ThreadMessagesResponse(BaseModel):
    messages: list[MessageRecord]
    widgets: list[WidgetSchema]
    thread_mode: Literal["ai", "human"] = "ai"


class ActionResponse(BaseModel):
    assistant_message: MessageRecord | None = None
    widget: WidgetSchema | None = None
    widget_id: str
    action_id: str


class AgentTakeoverRequest(BaseModel):
    thread_id: str
    agent_name: str = "Support Agent"


class AgentMessageRequest(BaseModel):
    thread_id: str
    agent_name: str = "Support Agent"
    text: str


class AgentReturnRequest(BaseModel):
    thread_id: str
    summary: str
    agent_name: str = "Support Agent"


class HumanMessageResponse(BaseModel):
    status: Literal["queued", "delivered"]
    thread_mode: Literal["human"]
    message: MessageRecord
