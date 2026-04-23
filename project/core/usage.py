COST_PER_MILLION_INPUT_TOKENS = 0.15
COST_PER_MILLION_OUTPUT_TOKENS = 0.60


def _calculate_cost(prompt_tokens: int, completion_tokens: int) -> float:
    input_cost = (
        prompt_tokens / 1_000_000
    ) * COST_PER_MILLION_INPUT_TOKENS
    output_cost = (
        completion_tokens / 1_000_000
    ) * COST_PER_MILLION_OUTPUT_TOKENS
    return round(input_cost + output_cost, 6)


def calculate_usage(usage_object) -> dict:
    if isinstance(usage_object, dict):
        prompt_tokens = usage_object.get(
            "prompt_tokens",
            usage_object.get("input_tokens", 0),
        )
        completion_tokens = usage_object.get(
            "completion_tokens",
            usage_object.get("output_tokens", 0),
        )
        total_tokens = usage_object.get(
            "total_tokens",
            prompt_tokens + completion_tokens,
        )
    else:
        prompt_tokens = getattr(
            usage_object,
            "prompt_tokens",
            getattr(usage_object, "input_tokens", 0),
        )
        completion_tokens = getattr(
            usage_object,
            "completion_tokens",
            getattr(usage_object, "output_tokens", 0),
        )
        total_tokens = getattr(
            usage_object,
            "total_tokens",
            prompt_tokens + completion_tokens,
        )

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": _calculate_cost(
            prompt_tokens,
            completion_tokens,
        ),
    }


def accumulate_usage(usage_list: list) -> dict:
    prompt_tokens = sum(item["prompt_tokens"] for item in usage_list)
    completion_tokens = sum(item["completion_tokens"] for item in usage_list)
    total_tokens = sum(item["total_tokens"] for item in usage_list)

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": _calculate_cost(
            prompt_tokens,
            completion_tokens,
        ),
    }
