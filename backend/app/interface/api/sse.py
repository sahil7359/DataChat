"""SSE frame formatting: an AgentEvent -> `event: <type>\\ndata: <json>\\n\\n`."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass

import orjson

from app.application.agent.events import AgentEvent


def format_sse(event: AgentEvent) -> str:
    payload = asdict(event) if is_dataclass(event) else {}
    payload.pop("type", None)
    data = orjson.dumps(payload, default=str).decode("utf-8")
    return f"event: {event.type}\ndata: {data}\n\n"
