"""Defines typed session and handoff state objects for orchestration."""

from typing import Literal, Optional

from pydantic import BaseModel, Field

from schemas.messages import ConversationMessage


class TriageEntities(BaseModel):
    """Carries lightweight entities extracted during triage classification."""

    account_id: Optional[str] = None
    issue: Optional[str] = None


class TriageHandoffPayload(BaseModel):
    """Defines the exact state passed from the Triage Agent to the next agent."""

    intent: Literal["billing", "technical_support", "general_inquiry"]
    entities: TriageEntities
    original_message: str
    conversation_summary: Optional[str] = None
    conversation_history: list[ConversationMessage] = Field(default_factory=list)


class BillingAgentResult(BaseModel):
    """Defines billing output plus the updated conversation state after response."""

    intent: Literal["billing", "technical_support", "general_inquiry"]
    entities: TriageEntities
    original_message: str
    response_text: str
    conversation_summary: Optional[str] = None
    conversation_history: list[ConversationMessage] = Field(default_factory=list)
