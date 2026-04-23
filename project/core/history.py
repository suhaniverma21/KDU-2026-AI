from copy import deepcopy


SUMMARY_PROMPT = (
    "Summarise the following conversation concisely. Preserve all "
    "important facts, decisions, questions asked, and answers given. "
    "Be brief but complete."
)


def needs_compaction(messages: list, max_turns: int = 10) -> bool:
    non_system_messages = [
        message for message in messages if message.get("role") != "system"
    ]
    return len(non_system_messages) > max_turns * 2


def compact_history(messages: list, client, max_turns: int = 10) -> list:
    compacted_messages = deepcopy(messages)
    system_message = None

    if compacted_messages and compacted_messages[0].get("role") == "system":
        system_message = compacted_messages[0]
        remaining_messages = compacted_messages[1:]
    else:
        remaining_messages = compacted_messages

    keep_count = max_turns * 2
    old_messages = remaining_messages[:-keep_count]
    recent_messages = remaining_messages[-keep_count:]

    if not old_messages:
        return compacted_messages

    response = client.responses.create(
        model="gpt-4o-mini",
        input=[
            {"role": "system", "content": SUMMARY_PROMPT},
            {"role": "user", "content": str(old_messages)},
        ],
    )

    summary = response.output_text
    summary_message = {
        "role": "system",
        "content": f"Summary of earlier conversation: {summary}",
    }

    result = []
    if system_message is not None:
        result.append(system_message)
    result.append(summary_message)
    result.extend(recent_messages)
    return result


def trim_history(messages: list, max_turns: int = 10) -> list:
    trimmed_messages = deepcopy(messages)

    if not trimmed_messages:
        return trimmed_messages

    system_message = None
    if trimmed_messages[0].get("role") == "system":
        system_message = trimmed_messages[0]
        remaining_messages = trimmed_messages[1:]
    else:
        remaining_messages = trimmed_messages

    kept_messages = remaining_messages[-(max_turns * 2) :]

    result = []
    if system_message is not None:
        result.append(system_message)
    result.extend(kept_messages)
    return result
