"""Explanation prompt (versioned). Grounds prose strictly in the returned rows
(LLM09 misinformation): the model is told to cite concrete numbers from the data
and to admit when there is no data, not to embellish."""

from __future__ import annotations

from app.domain.entities import ExecutionResult, LLMMessage, MessageRole

EXPLANATION_VERSION = "explanation@v1"

_SYSTEM = (
    "You explain query results to a non-technical reader in 2-3 sentences. "
    "Ground every claim ONLY in the rows provided; cite concrete numbers. "
    "If there are no rows, say the data did not contain an answer. Do not invent."
)

_MAX_ROWS = 20


def build_explanation_messages(question: str, execution: ExecutionResult) -> tuple[LLMMessage, ...]:
    user = f"Question: {question}\n\nResult ({execution.row_count} rows):\n{_render(execution)}"
    return (
        LLMMessage(MessageRole.SYSTEM, _SYSTEM),
        LLMMessage(MessageRole.USER, user),
    )


def _render(execution: ExecutionResult) -> str:
    header = " | ".join(execution.columns)
    body = "\n".join(" | ".join(str(cell) for cell in row) for row in execution.rows[:_MAX_ROWS])
    return f"{header}\n{body}" if body else "(no rows)"
