"""Defines message envelopes for user turns, agent replies, and tool outcomes."""

from typing import Literal

from pydantic import BaseModel


class ConversationMessage(BaseModel):
    """Represents one preserved turn in the conversation history handoff."""

    role: Literal["user", "assistant"]
    content: str
