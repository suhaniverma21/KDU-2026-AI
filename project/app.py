import os
import json

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request, stream_with_context

from core.logger import log_request
from core.usage import accumulate_usage
from pipeline.conversation import run_conversation
from pipeline.input_guardrail import validate_input


REQUIRED_ENV_VARS = (
    "OPENAI_API_KEY",
    "WEATHER_API_KEY",
    "SERPER_API_KEY",
)


def load_and_validate_environment() -> None:
    load_dotenv()

    missing_keys = [
        key
        for key in REQUIRED_ENV_VARS
        if not os.getenv(key) or os.getenv(key) == "your-key-here"
    ]

    if missing_keys:
        missing = ", ".join(missing_keys)
        raise RuntimeError(
            f"Missing required environment variables: {missing}. "
            "Update the .env file before starting the server."
        )


load_and_validate_environment()

app = Flask(__name__, static_folder="static")


@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    payload = request.get_json(silent=True) or {}
    messages = payload.get("messages", [])

    last_user_message = ""
    for message in reversed(messages):
        if message.get("role") == "user":
            last_user_message = message.get("content", "")
            break

    is_valid, error_message = validate_input(last_user_message)
    if not is_valid:
        log_request(
            {
                "total_tokens": 0,
                "estimated_cost_usd": 0,
                "tool_used": "none",
                "input_guardrail_triggered": True,
                "success": False,
                "error": error_message,
            }
        )
        return (
            jsonify(
                {
                    "error_code": "INPUT_REJECTED",
                    "message": error_message,
                    "retryable": False,
                }
            ),
            400,
        )

    try:
        response_text, usage_list = run_conversation(messages)
    except Exception as exc:
        log_request(
            {
                "total_tokens": 0,
                "estimated_cost_usd": 0,
                "tool_used": getattr(run_conversation, "last_tool_used", "none"),
                "input_guardrail_triggered": False,
                "success": False,
                "error": str(exc),
            }
        )
        return (
            jsonify(
                {
                    "error_code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred",
                    "retryable": False,
                }
            ),
            500,
        )

    accumulated_usage = accumulate_usage(usage_list)
    log_request(
        {
            "total_tokens": accumulated_usage["total_tokens"],
            "estimated_cost_usd": accumulated_usage["estimated_cost_usd"],
            "tool_used": getattr(run_conversation, "last_tool_used", "none"),
            "input_guardrail_triggered": False,
            "success": True,
            "error": None,
        }
    )

    @stream_with_context
    def generate():
        for word in response_text.split():
            yield f"data: {json.dumps({'type': 'text', 'content': word + ' '})}\n\n"

        yield f"data: {json.dumps({'type': 'usage', 'data': accumulated_usage})}\n\n"
        yield "data: [DONE]\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    app.run(debug=True)
