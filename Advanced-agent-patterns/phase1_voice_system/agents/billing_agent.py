"""Handles billing-specific customer requests after triage handoff."""

from __future__ import annotations

from agents.base import BaseAgent
from audio.playback import PlaybackController
from config.settings import Settings, get_settings
from schemas.messages import ConversationMessage
from schemas.state import BillingAgentResult, TriageHandoffPayload
from services.openai_client import get_openai_client


BILLING_SYSTEM_PROMPT = (
    "You handle billing issues. Use prior conversation context. "
    "Reply briefly and helpfully."
)


class BillingAgent(BaseAgent):
    """Generates a billing response from transferred triage state and speaks it aloud."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = get_openai_client()

    def run(
        self,
        handoff_payload: dict,
        playback: PlaybackController | None = None,
    ) -> dict:
        """Accept triage handoff state, respond with context, and update history."""
        state = TriageHandoffPayload.model_validate(handoff_payload)
        response_text = self._generate_response(state)
        updated_history = list(state.conversation_history)
        updated_history.append(
            ConversationMessage(role="assistant", content=response_text)
        )

        playback_controller = playback or PlaybackController(self.settings)
        playback_controller.play_text(response_text)

        result = BillingAgentResult(
            intent=state.intent,
            entities=state.entities,
            original_message=state.original_message,
            response_text=response_text,
            conversation_summary=state.conversation_summary,
            conversation_history=updated_history,
        )
        return result.model_dump()

    def _generate_response(self, state: TriageHandoffPayload) -> str:
        """Generate a billing reply using the transferred conversation state."""
        completion = self.client.chat.completions.create(
            model=self.settings.default_llm_model,
            messages=self._build_messages(state),
        )
        return (completion.choices[0].message.content or "").strip()

    def _build_messages(self, state: TriageHandoffPayload) -> list[dict[str, str]]:
        """Build the billing prompt from handoff fields so prior context is preserved."""
        messages: list[dict[str, str]] = [
            {"role": "system", "content": BILLING_SYSTEM_PROMPT},
            {
                "role": "assistant",
                "content": (
                    "Transferred triage state:\n"
                    f"- intent: {state.intent}\n"
                    f"- account_id: {state.entities.account_id}\n"
                    f"- issue: {state.entities.issue}\n"
                    f"- original_message: {state.original_message}"
                ),
            },
        ]

        if state.conversation_summary:
            messages.append(
                {
                    "role": "assistant",
                    "content": (
                        "Summary of earlier conversation:\n"
                        f"{state.conversation_summary}"
                    ),
                }
            )

        for turn in state.conversation_history:
            messages.append({"role": turn.role, "content": turn.content})

        return messages


def build_billing_handoff_example(handoff_payload: dict) -> dict:
    """Show exactly what transferred state the Billing Agent consumes and extends."""
    state = TriageHandoffPayload.model_validate(handoff_payload)
    return {
        "received_intent": state.intent,
        "received_entities": {
            "account_id": state.entities.account_id,
            "issue": state.entities.issue,
        },
        "received_original_message": state.original_message,
        "received_conversation_summary": state.conversation_summary,
        "received_conversation_history": [
            {"role": turn.role, "content": turn.content}
            for turn in state.conversation_history
        ],
        "billing_agent_action": (
            "Use the transferred conversation_summary, recent conversation_history, and "
            "triage entities to answer without restarting from scratch, then append the "
            "billing reply."
        ),
    }
