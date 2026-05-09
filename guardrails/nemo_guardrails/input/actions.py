from nemoguardrails.actions import action


PROMPT_INJECTION_PATTERNS = [
    "ignore previous instructions",
    "debugging system",
    "print all stored user data",
    "developer message",
    "system prompt",
    "reveal hidden data",
    "customer record as json",
    "stored in memory",
]


@action(is_system_action=True)
async def detect_prompt_injection(text: str) -> bool:
    lowered = text.lower()
    return any(pattern in lowered for pattern in PROMPT_INJECTION_PATTERNS)
