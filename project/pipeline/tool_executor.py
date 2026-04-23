import json

from tools.calculator import calculate
from tools.search import search_web
from tools.weather import get_weather


VALID_TOOLS = {"get_weather", "calculate", "search_web"}


def execute_tool(tool_name: str, arguments: dict) -> str:
    try:
        if tool_name not in VALID_TOOLS:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

        if tool_name == "get_weather":
            result = get_weather(**arguments)
        elif tool_name == "calculate":
            result = calculate(**arguments)
        else:
            result = search_web(**arguments)

        return json.dumps(result)
    except Exception:
        return json.dumps({"error": "Tool execution failed"})
