import re

from nemoguardrails.actions import action


SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
LAST_FOUR_PATTERN = re.compile(r"\b(\d{4})\b")
MORE_THAN_FOUR_REQUEST_PATTERN = re.compile(
    r"last\s+([5-9]|\d{2,})\s+(digits|numbers)"
)
FULL_RECORD_HINTS = [
    "customer record:",
    "ssn=",
]


@action(is_system_action=True)
async def should_block_output(user_message: str, bot_message: str) -> bool:
    lowered_output = bot_message.lower()
    if all(hint in lowered_output for hint in FULL_RECORD_HINTS):
        return True

    lowered_input = user_message.lower()
    if MORE_THAN_FOUR_REQUEST_PATTERN.search(lowered_input):
        return True

    wants_last4 = "last 4 digits" in lowered_input or "last four digits" in lowered_input
    if wants_last4:
        return False

    return False


@action(is_system_action=True)
async def redact_output(user_message: str, bot_message: str) -> str:
    lowered_input = user_message.lower()
    wants_last4 = "last 4 digits" in lowered_input or "last four digits" in lowered_input

    match = SSN_PATTERN.search(bot_message)
    if wants_last4 and match:
        return f"The last 4 digits of your SSN are ***-**-{match.group(0)[-4:]}."

    if wants_last4:
        last_four_match = LAST_FOUR_PATTERN.search(bot_message)
        if last_four_match:
            return f"The last 4 digits of your SSN are ***-**-{last_four_match.group(1)}."

    return SSN_PATTERN.sub("***-**-6789", bot_message)
