import os
import json

import requests

from core.history import trim_history
from core.retry import call_with_retry
from core.schemas import TOOLS
from core.usage import calculate_usage
from pipeline.tool_executor import execute_tool


MODEL = "gpt-4o-mini"
SYSTEM_PROMPT = (
    "You are a helpful assistant with access to weather, calculator, "
    "and web search tools. Use tools when needed to give accurate "
    "answers. For general questions answer directly without using tools."
)
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


def _split_instructions_and_messages(messages: list) -> tuple[str, list]:
    trimmed_messages = trim_history(messages)

    if trimmed_messages and trimmed_messages[0].get("role") == "system":
        instructions = trimmed_messages[0].get("content", SYSTEM_PROMPT)
        input_messages = [dict(message) for message in trimmed_messages[1:]]
    else:
        instructions = SYSTEM_PROMPT
        input_messages = [dict(message) for message in trimmed_messages]

    return instructions, input_messages


def _responses_tools() -> list:
    response_tools = []

    for tool in TOOLS:
        function_tool = tool["function"]
        response_tools.append(
            {
                "type": "function",
                "name": function_tool["name"],
                "description": function_tool["description"],
                "parameters": function_tool["parameters"],
            }
        )

    return response_tools


def _create_response(
    *,
    instructions: str,
    input_items: list,
    previous_response_id: str | None = None,
    tools: list | None = None,
) -> dict:
    api_key = os.getenv("OPENAI_API_KEY")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "instructions": instructions,
        "input": input_items,
    }

    if previous_response_id is not None:
        payload["previous_response_id"] = previous_response_id
    if tools is not None:
        payload["tools"] = tools

    response = requests.post(
        OPENAI_RESPONSES_URL,
        headers=headers,
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def _extract_output_text(response: dict) -> str:
    output_text = []

    for item in response.get("output", []):
        if item.get("type") != "message":
            continue

        for content_item in item.get("content", []):
            if content_item.get("type") in {"output_text", "text"}:
                output_text.append(content_item.get("text", ""))

    return "".join(output_text).strip()


def _get_function_calls(response: dict) -> list:
    return [
        item
        for item in response.get("output", [])
        if item.get("type") == "function_call"
    ]


def _execute_function_calls(function_calls: list) -> list:
    outputs = []

    for function_call in function_calls:
        run_conversation.last_tool_used = function_call["name"]
        arguments = json.loads(function_call["arguments"])
        tool_result = execute_tool(function_call["name"], arguments)
        outputs.append(
            {
                "type": "function_call_output",
                "call_id": function_call["call_id"],
                "output": tool_result,
            }
        )

    return outputs


def run_conversation(messages: list) -> tuple[str, list]:
    run_conversation.last_tool_used = "none"
    instructions, input_messages = _split_instructions_and_messages(messages)
    usage_list = []
    response_tools = _responses_tools()

    response = call_with_retry(
        lambda: _create_response(
            instructions=instructions,
            input_items=input_messages,
            tools=response_tools,
        )
    )
    usage_list.append(calculate_usage(response.get("usage", {})))

    function_calls = _get_function_calls(response)
    if not function_calls:
        return _extract_output_text(response), usage_list

    previous_response_id = response["id"]
    tool_rounds = 1

    while function_calls:
        tool_outputs = _execute_function_calls(function_calls)

        if tool_rounds >= 3:
            tool_outputs.append(
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Please give your final answer now"}],
                }
            )
            final_response = call_with_retry(
                lambda: _create_response(
                    instructions=instructions,
                    input_items=tool_outputs,
                    previous_response_id=previous_response_id,
                )
            )
            usage_list.append(calculate_usage(final_response.get("usage", {})))
            return _extract_output_text(final_response), usage_list

        response = call_with_retry(
            lambda: _create_response(
                instructions=instructions,
                input_items=tool_outputs,
                previous_response_id=previous_response_id,
                tools=response_tools,
            )
        )
        usage_list.append(calculate_usage(response.get("usage", {})))

        function_calls = _get_function_calls(response)
        if not function_calls:
            return _extract_output_text(response), usage_list

        previous_response_id = response["id"]
        tool_rounds += 1

    return _extract_output_text(response), usage_list
