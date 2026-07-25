"""SSE event model (TechSpec §4).

The agent's progress is published as a small tagged set of events. The BFF turns
each into an ``event: <type>\\ndata: <json>\\n\\n`` frame. Keeping the event types
here (application layer) means the graph decides *what* happened; the transport
layer only formats it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StatusEvent:
    stage: str
    type: str = "status"


@dataclass(frozen=True, slots=True)
class PlanEvent:
    steps: Sequence[str]
    target_tables: Sequence[str]
    type: str = "plan"


@dataclass(frozen=True, slots=True)
class SqlEvent:
    sql: str
    type: str = "sql"


@dataclass(frozen=True, slots=True)
class AwaitingApprovalEvent:
    run_id: str
    kind: str  # "approve" | "clarify"
    sql: str | None = None
    options: Sequence[str] = ()
    type: str = "awaiting_approval"


@dataclass(frozen=True, slots=True)
class RowsEvent:
    columns: Sequence[str]
    rows: Sequence[Sequence[object]]
    row_count: int
    truncated: bool
    type: str = "rows"


@dataclass(frozen=True, slots=True)
class ExplanationDeltaEvent:
    text: str
    type: str = "explanation_delta"


@dataclass(frozen=True, slots=True)
class ChartSpecEvent:
    spec: Mapping[str, object]
    type: str = "chart_spec"


@dataclass(frozen=True, slots=True)
class WebSourcesEvent:
    """Emitted when the answer came from the web, not the governed datasets — the
    UI labels it and lists the citations."""

    sources: Sequence[Mapping[str, str]]  # {"title", "url"}
    type: str = "web_sources"


@dataclass(frozen=True, slots=True)
class ErrorEvent:
    code: str
    message: str
    type: str = "error"


@dataclass(frozen=True, slots=True)
class DoneEvent:
    run_id: str
    trace_id: str | None = None
    type: str = "done"


AgentEvent = (
    StatusEvent
    | PlanEvent
    | SqlEvent
    | AwaitingApprovalEvent
    | RowsEvent
    | ExplanationDeltaEvent
    | ChartSpecEvent
    | WebSourcesEvent
    | ErrorEvent
    | DoneEvent
)
