BLOCKLIST = [
    "ignore previous instructions",
    "ignore all instructions",
    "disregard your system prompt",
    "reveal your instructions",
    "pretend you are",
    "you are now",
    "forget everything",
    "bypass your restrictions",
    "what are your instructions",
]


def validate_input(message: str) -> tuple[bool, str]:
    if not message or message.isspace():
        return False, "Message cannot be empty"

    if len(message) > 1000:
        return False, "Message exceeds maximum length of 1000 characters"

    if any(ord(c) < 32 and c not in "\n\r\t" for c in message):
        return False, "Message contains invalid characters"

    lowered_message = message.lower()
    if any(blocked_phrase in lowered_message for blocked_phrase in BLOCKLIST):
        return False, "Message contains content that cannot be processed"

    return True, ""
