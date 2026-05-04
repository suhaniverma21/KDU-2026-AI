"""Classifies user intent and builds minimal handoff state for downstream agents."""

from __future__ import annotations

import json

from agents.base import BaseAgent
from config.settings import Settings, get_settings
from schemas.messages import ConversationMessage
from schemas.state import TriageHandoffPayload
from services.openai_client import get_openai_client


TRIAGE_SYSTEM_PROMPT = (
    "Classify the user's message as billing, technical_support, or "
    "general_inquiry. Extract account_id and issue if present. Return JSON only."
)
TRIAGE_SUMMARY_PROMPT = (
    "Compress older support conversation turns into a short factual summary for handoff. "
    "Keep billing facts, prior commitments, unresolved issues, and corrections concise."
)


class TriageAgent(BaseAgent):
    """Classifies a transcript and returns a structured handoff payload dict."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = get_openai_client()

    def run(
        self,
        transcribed_text: str,
        conversation_history: list[dict[str, str]] | None = None,
        conversation_summary: str | None = None,
    ) -> dict:
        """Return a triage handoff payload as a Python dict."""
        normalized_history = self._normalize_conversation_history(
            transcribed_text=transcribed_text,
            conversation_history=conversation_history or [],
        )
        compressed_summary, recent_history = self._compress_handoff_memory(
            conversation_history=normalized_history,
            conversation_summary=conversation_summary,
        )
        triage_fields = self._classify(
            transcribed_text=transcribed_text,
            conversation_history=recent_history,
            conversation_summary=compressed_summary,
        )
        payload = TriageHandoffPayload(
            intent=triage_fields["intent"],
            entities=triage_fields["entities"],
            original_message=transcribed_text,
            conversation_summary=compressed_summary,
            conversation_history=recent_history,
        )
        return payload.model_dump()

    def _classify(
        self,
        transcribed_text: str,
        conversation_history: list[ConversationMessage],
        conversation_summary: str | None,
    ) -> dict:
        """Call Chat Completions and parse the compact triage JSON response."""
        completion = self.client.chat.completions.create(
            model=self.settings.default_llm_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": TRIAGE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": self._build_user_prompt(
                        transcribed_text=transcribed_text,
                        conversation_history=conversation_history,
                        conversation_summary=conversation_summary,
                    ),
                },
            ],
        )
        content = completion.choices[0].message.content or "{}"
        parsed = json.loads(content)
        return {
            "intent": parsed["intent"],
            "entities": {
                "account_id": parsed.get("entities", {}).get("account_id"),
                "issue": parsed.get("entities", {}).get("issue"),
            },
        }

    @staticmethod
    def _normalize_conversation_history(
        transcribed_text: str,
        conversation_history: list[dict[str, str]],
    ) -> list[ConversationMessage]:
        """Keep only user and assistant turns, then append the latest user message."""
        normalized: list[ConversationMessage] = []
        for turn in conversation_history:
            role = turn.get("role")
            content = turn.get("content", "").strip()
            if role in {"user", "assistant"} and content:
                normalized.append(ConversationMessage(role=role, content=content))

        normalized.append(ConversationMessage(role="user", content=transcribed_text))
        return normalized

    @staticmethod
    def _build_user_prompt(
        transcribed_text: str,
        conversation_history: list[ConversationMessage],
        conversation_summary: str | None,
    ) -> str:
        """Show the model exactly which turns are included in the handoff history."""
        history_lines = [
            f"- {message.role}: {message.content}" for message in conversation_history
        ]
        joined_history = "\n".join(history_lines) if history_lines else "- user: "
        summary_section = (
            f"summary_of_earlier_conversation:\n{conversation_summary}\n\n"
            if conversation_summary
            else ""
        )
        return (
            "Return JSON with this schema: "
            '{"intent":"billing|technical_support|general_inquiry",'
            '"entities":{"account_id":null,"issue":null}}'
            "\n\n"
            "Latest transcribed user text:\n"
            f"{transcribed_text}\n\n"
            f"{summary_section}"
            "conversation_history included in handoff:\n"
            f"{joined_history}"
        )

    def _compress_handoff_memory(
        self,
        conversation_history: list[ConversationMessage],
        conversation_summary: str | None,
    ) -> tuple[str | None, list[ConversationMessage]]:
        """Keep the last 6 turns and roll any older turns into a compact handoff summary."""
        recent_turn_limit = 6
        if len(conversation_history) <= recent_turn_limit:
            return conversation_summary, conversation_history

        older_turns = conversation_history[:-recent_turn_limit]
        recent_turns = conversation_history[-recent_turn_limit:]
        updated_summary = self._summarize_older_turns(
            older_turns=older_turns,
            existing_summary=conversation_summary,
        )
        return updated_summary, recent_turns

    def _summarize_older_turns(
        self,
        older_turns: list[ConversationMessage],
        existing_summary: str | None,
    ) -> str:
        """Summarize older turns so handoffs preserve context without replaying every message."""
        older_lines = [f"- {turn.role}: {turn.content}" for turn in older_turns]
        summary_context = existing_summary or "None"
        completion = self.client.chat.completions.create(
            model=self.settings.default_llm_model,
            messages=[
                {"role": "system", "content": TRIAGE_SUMMARY_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"existing_summary:\n{summary_context}\n\n"
                        "older_turns_to_roll_up:\n"
                        + "\n".join(older_lines)
                    ),
                },
            ],
        )
        return (completion.choices[0].message.content or "").strip()
