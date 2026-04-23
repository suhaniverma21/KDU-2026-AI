GET_WEATHER_TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": (
            "Get current weather for a city. Use this when the user asks "
            "about weather, temperature, or climate conditions in a location."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "The city to get the current weather for.",
                },
                "unit": {
                    "type": "string",
                    "enum": ["celsius", "fahrenheit"],
                    "default": "celsius",
                    "description": "The temperature unit to use.",
                },
            },
            "required": ["city"],
            "additionalProperties": False,
        },
    },
}

CALCULATE_TOOL = {
    "type": "function",
    "function": {
        "name": "calculate",
        "description": (
            "Evaluate a mathematical expression. Use this for arithmetic, "
            "percentages, exponents, or any numerical computation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": (
                        "The expression to evaluate, for example '2 ** 10' "
                        "or 'sqrt(144)'."
                    ),
                }
            },
            "required": ["expression"],
            "additionalProperties": False,
        },
    },
}

SEARCH_WEB_TOOL = {
    "type": "function",
    "function": {
        "name": "search_web",
        "description": (
            "Search the web for current information. Use this for recent "
            "events, factual lookups, or anything that may have changed "
            "after the model training cutoff."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to look up on the web.",
                }
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}

TOOLS = [
    GET_WEATHER_TOOL,
    CALCULATE_TOOL,
    SEARCH_WEB_TOOL,
]
