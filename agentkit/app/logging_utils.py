from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from app.models import LogEvent


class StructuredLogger:
    def __init__(self, sink_path: Path | None = None) -> None:
        self.sink_path = sink_path
        self.events: list[dict[str, object]] = []

    def log(self, event: LogEvent) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **asdict(event),
        }
        self.events.append(record)
        if self.sink_path is not None:
            self.sink_path.parent.mkdir(parents=True, exist_ok=True)
            with self.sink_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")
