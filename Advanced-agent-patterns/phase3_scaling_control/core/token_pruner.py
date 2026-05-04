"""Prunes conversation history to control token growth during agent handoffs."""

from __future__ import annotations

import math
from typing import Any

from openai import OpenAI

from config.settings import get_settings


class TokenPruner:
    """Applies staged pruning strategies to keep handoff histories within token budgets."""

    def __init__(self) -> None:
        """Initialize the pruner with environment-backed settings and an OpenAI client."""
        self.settings = get_settings()
        self.client = OpenAI(api_key=self.settings.openai_api_key)

    def prune(
        self,
        conversation_history: list[dict[str, str]],
        max_tokens: int,
    ) -> dict[str, Any]:
        """Prune a conversation history using windowing, summarization, and truncation."""
        original_history = [dict(message) for message in conversation_history]
        original_token_count = self.estimate_tokens(original_history)

        # Step 1 exists because the cheapest and safest option is to preserve the full
        # history whenever it already fits inside the handoff token budget.
        if original_token_count <= max_tokens:
            return self._build_result(
                pruned_history=original_history,
                original_token_count=original_token_count,
                strategy_used="none",
                messages_removed=0,
            )

        # Step 2 exists because a recency window often solves token bloat without losing
        # the most relevant turns for the next agent.
        windowed_history = self._apply_window_strategy(original_history)
        windowed_token_count = self.estimate_tokens(windowed_history)
        if windowed_token_count <= max_tokens:
            return self._build_result(
                pruned_history=windowed_history,
                original_token_count=original_token_count,
                strategy_used="window",
                messages_removed=len(original_history) - len(windowed_history),
            )

        # Step 3 exists because when recency alone is still too large, summarization keeps
        # older facts alive while compressing them into one message for the handoff.
        summarized_history = self._apply_summary_strategy(original_history)
        summarized_token_count = self.estimate_tokens(summarized_history)
        if summarized_token_count <= max_tokens:
            return self._build_result(
                pruned_history=summarized_history,
                original_token_count=original_token_count,
                strategy_used="summarize",
                messages_removed=len(original_history) - len(summarized_history),
            )

        # Step 4 exists as a final safety valve that guarantees bounded message arrays
        # even under extreme load or unusually long conversations.
        truncated_history = self._apply_truncate_strategy(summarized_history, max_tokens)
        return self._build_result(
            pruned_history=truncated_history,
            original_token_count=original_token_count,
            strategy_used="truncate",
            messages_removed=len(original_history) - len(truncated_history),
        )

    def estimate_tokens(self, messages: list[dict[str, str]]) -> int:
        """Estimate token count locally using the rough rule that 1 token is about 4 chars."""
        total_characters = 0
        for message in messages:
            total_characters += len(message.get("role", ""))
            total_characters += len(message.get("content", ""))
        return math.ceil(total_characters / 4)

    def summarize_old_messages(
        self,
        messages: list[dict[str, str]],
    ) -> dict[str, str]:
        """Compress older messages into a single summary message using `gpt-4o-mini`."""
        if not messages:
            return {"role": "assistant", "content": "Summary: no earlier context available."}

        prompt_lines = [
            f"{message.get('role', 'unknown')}: {message.get('content', '')}"
            for message in messages
        ]
        completion = self.client.chat.completions.create(
            model="gpt-4o-mini",
            timeout=30,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Summarize older conversation context for agent handoff. "
                        "Keep facts, intents, unresolved issues, and commitments concise."
                    ),
                },
                {
                    "role": "user",
                    "content": "\n".join(prompt_lines),
                },
            ],
        )
        summary_text = (completion.choices[0].message.content or "").strip()
        return {
            "role": "assistant",
            "content": f"Summary of earlier conversation: {summary_text}",
        }

    def _apply_window_strategy(
        self,
        messages: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        """Keep the system message and the most recent configured exchanges."""
        # Why this exists:
        # Windowing is the cheapest first reduction step because it preserves the freshest
        # conversational turns while dropping older turns that are less likely to matter.
        system_message, non_system_messages = self._split_system_message(messages)
        exchanges_to_keep = self.settings.summary_keep_last_n_exchanges * 2
        recent_messages = non_system_messages[-exchanges_to_keep:]
        return self._combine_messages(system_message, recent_messages)

    def _apply_summary_strategy(
        self,
        messages: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        """Summarize everything except the latest two exchanges into one compact message."""
        # Why this exists:
        # Summarization is used only after windowing fails because it trades precision for
        # compactness, preserving long-range context without carrying all raw messages.
        system_message, non_system_messages = self._split_system_message(messages)
        if len(non_system_messages) <= 4:
            return self._combine_messages(system_message, non_system_messages)

        recent_messages = non_system_messages[-4:]
        older_messages = non_system_messages[:-4]
        summary_message = self.summarize_old_messages(older_messages)
        return self._combine_messages(system_message, [summary_message, *recent_messages])

    def _apply_truncate_strategy(
        self,
        messages: list[dict[str, str]],
        max_tokens: int,
    ) -> list[dict[str, str]]:
        """Drop oldest non-system messages until the history fits inside the token budget."""
        # Why this exists:
        # Hard truncation is the last-resort safety valve when even summarization cannot fit
        # the handoff inside budget; it guarantees bounded size under extreme load.
        system_message, non_system_messages = self._split_system_message(messages)
        pruned_messages = list(non_system_messages)

        while pruned_messages and self.estimate_tokens(
            self._combine_messages(system_message, pruned_messages)
        ) > max_tokens:
            pruned_messages.pop(0)

        return self._combine_messages(system_message, pruned_messages)

    def _build_result(
        self,
        pruned_history: list[dict[str, str]],
        original_token_count: int,
        strategy_used: str,
        messages_removed: int,
    ) -> dict[str, Any]:
        """Build the standardized pruning response payload."""
        return {
            "pruned_history": pruned_history,
            "pruning_report": {
                "original_token_count": original_token_count,
                "pruned_token_count": self.estimate_tokens(pruned_history),
                "strategy_used": strategy_used,
                "messages_removed": max(0, messages_removed),
            },
        }

    @staticmethod
    def _split_system_message(
        messages: list[dict[str, str]],
    ) -> tuple[dict[str, str] | None, list[dict[str, str]]]:
        """Split the first system message from the rest of the conversation history."""
        system_message: dict[str, str] | None = None
        remaining_messages: list[dict[str, str]] = []

        for message in messages:
            if system_message is None and message.get("role") == "system":
                system_message = dict(message)
            else:
                remaining_messages.append(dict(message))

        return system_message, remaining_messages

    @staticmethod
    def _combine_messages(
        system_message: dict[str, str] | None,
        non_system_messages: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        """Rebuild the message list while ensuring the system message is never removed."""
        combined_messages: list[dict[str, str]] = []
        if system_message is not None:
            combined_messages.append(system_message)
        combined_messages.extend(non_system_messages)
        return combined_messages
