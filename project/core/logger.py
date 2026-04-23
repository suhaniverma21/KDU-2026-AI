import json
from datetime import datetime
from pathlib import Path


LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "requests.log"


def log_request(data: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "total_tokens": data.get("total_tokens", 0),
        "estimated_cost_usd": data.get("estimated_cost_usd", 0),
        "tool_used": data.get("tool_used", "none"),
        "input_guardrail_triggered": data.get(
            "input_guardrail_triggered",
            False,
        ),
        "success": data.get("success", False),
        "error": data.get("error"),
    }

    with LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(log_entry) + "\n")
