"""Simple helper functions for style-based prompt behavior.

In this project, "middleware" means shared logic that prepares behavior
for other parts of the app. We are not using a real FastAPI middleware
class here. Instead, we keep the style logic in one reusable module so
the endpoint code stays smaller and easier to maintain.
"""


def normalize_style(style: str | None) -> str:
    """Return a safe style value.

    This keeps the rest of the code simple:
    - None becomes casual
    - mixed-case values like "Expert" become expert
    - unknown values also fall back to casual
    """
    if not style:
        return "casual"

    cleaned_style = style.strip().lower()
    if cleaned_style in {"expert", "child", "casual"}:
        return cleaned_style
    return "casual"


def detect_tone_override(message: str) -> str | None:
    """Look for simple temporary tone requests in the user's message.

    This lets the user override the saved default style for one message,
    such as asking for a simpler or more technical explanation.
    """
    lowered = (message or "").lower()

    if "explain simply" in lowered or "simple words" in lowered or "i am confused" in lowered:
        return "child"

    if "be technical" in lowered or "technical" in lowered or "in detail" in lowered:
        return "expert"

    if "be brief" in lowered or "briefly" in lowered or "short answer" in lowered:
        return "brief"

    return None


def get_style_instruction(style: str) -> str:
    """Return the instruction text for one style."""
    normalized_style = normalize_style(style)

    if normalized_style == "expert":
        return "Respond with technical depth, precise explanations, and correct terminology."
    if normalized_style == "child":
        return (
            "Explain in very simple words like you are talking to a 10-year-old. "
            "Avoid complex terms and jargon."
        )
    return "Be friendly, conversational, and easy to understand."


def get_final_tone_instruction(saved_style: str | None, message: str) -> tuple[str, str]:
    """Combine the saved profile style with a temporary message override.

    The saved profile gives the default tone. The current message can adjust
    that tone for just one request. This only changes tone, not safety rules.
    """
    base_style = normalize_style(saved_style)
    override = detect_tone_override(message)

    if override == "brief":
        return base_style, "Keep the answer short and focused."

    if override == "expert":
        return "expert", get_style_instruction("expert")

    if override == "child":
        return "child", get_style_instruction("child")

    return base_style, get_style_instruction(base_style)


def apply_style_to_system_prompt(base_prompt: str, style: str) -> str:
    """Combine the base prompt with the style instruction.

    Separating this from the endpoint means style behavior can be reused
    anywhere we need prompt preparation.
    """
    normalized_style = normalize_style(style)
    style_instruction = get_style_instruction(normalized_style)
    return f"{base_prompt} {style_instruction}"


def apply_dynamic_style_to_system_prompt(
    base_prompt: str,
    saved_style: str | None,
    message: str,
) -> tuple[str, str]:
    """Build the final system prompt using default style plus overrides.

    Safety stays in the base prompt. Style only changes how we explain things.
    """
    final_style, final_instruction = get_final_tone_instruction(saved_style, message)
    return f"{base_prompt} {final_instruction}", final_style
