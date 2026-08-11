"""Domain entities — the nouns of DataChat.

All immutable (``frozen``) so state transitions are explicit: a node returns a
new object rather than mutating one in place, which keeps the LangGraph state
reducers honest and makes checkpoints trivially serialisable.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from app.domain.value_objects import (
    ActionType,
    ConversationId,
    DatasetId,
    HITLDecision,
    Provider,
    RunId,
    TaskKind,
    TurnId,
    TurnRole,
)

# --- Conversations & turns -------------------------------------------------


@dataclass(frozen=True, slots=True)
class Turn:
    id: TurnId
    conversation_id: ConversationId
    role: TurnRole
    content: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Conversation:
    id: ConversationId
    title: str
    created_at: datetime
    updated_at: datetime
    user_ref: str | None = None
    turns: tuple[Turn, ...] = ()


# --- Semantic layer / retrieval -------------------------------------------


@dataclass(frozen=True, slots=True)
class ColumnDoc:
    column_name: str
    data_type: str
    description: str
    unit: str | None = None
    synonyms: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TableDoc:
    table_name: str
    description: str
    columns: tuple[ColumnDoc, ...] = ()
    score: float = 0.0


@dataclass(frozen=True, slots=True)
class Example:
    """A curated few-shot NL->SQL pair used to ground generation."""

    question: str
    sql: str
    tags: tuple[str, ...] = ()
    score: float = 0.0


@dataclass(frozen=True, slots=True)
class RetrievedContext:
    tables: tuple[TableDoc, ...] = ()
    examples: tuple[Example, ...] = ()

    def is_empty(self) -> bool:
        return not self.tables and not self.examples


@dataclass(frozen=True, slots=True)
class Dataset:
    id: DatasetId
    name: str
    source: str
    version: str
    checksum: str
    description: str


# --- Planning & SQL --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Plan:
    steps: tuple[str, ...]
    target_tables: tuple[str, ...] = ()
    needs_chart: bool = False


@dataclass(frozen=True, slots=True)
class RuleResult:
    """Outcome of one guardrail rule (a single link in the chain)."""

    rule: str
    passed: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ValidationResult:
    ok: bool
    sql: str
    results: tuple[RuleResult, ...] = ()

    @property
    def violations(self) -> tuple[RuleResult, ...]:
        return tuple(r for r in self.results if not r.passed)

    @property
    def first_violation(self) -> RuleResult | None:
        return self.violations[0] if self.violations else None


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    columns: tuple[str, ...]
    rows: tuple[tuple[object, ...], ...]
    row_count: int
    elapsed_ms: int
    truncated: bool = False

    def is_empty(self) -> bool:
        return self.row_count == 0


@dataclass(frozen=True, slots=True)
class WebResult:
    """One untrusted web search hit. Its text is data for the model to summarise,
    never an instruction to follow (the web-answer prompt is hardened accordingly)."""

    title: str
    url: str
    snippet: str


@dataclass(frozen=True, slots=True)
class WebTableRow:
    """One extracted row. ``values`` aligns positionally with ``WebTable.columns``
    and carries ``None`` wherever the sources did not state a value.

    ``source_index`` is a 1-based index into the ``WebResult`` tuple the row was
    read from. It is mandatory: a row nobody can attribute is a row we drop.
    """

    values: tuple[object, ...]
    source_index: int


@dataclass(frozen=True, slots=True)
class WebTable:
    """Tabular data read out of untrusted web snippets.

    why: deliberately *not* an ``ExecutionResult``. Governed SQL output is verified
    against a read-only role and an AST guardrail; this is a language model's
    reading of search snippets. Giving them one type would make them substitutable
    in the UI, the report and the cache, and the whole safety story of this project
    rests on a user being able to tell them apart.
    alt: reuse ExecutionResult with a provenance flag (fewer types, but one missed
    flag check silently launders web scrapings as governed data).

    ``caveat`` carries the model's own statement of what is missing or uncertain,
    which is rendered with the table rather than buried.
    """

    columns: tuple[str, ...]
    rows: tuple[WebTableRow, ...]
    caveat: str = ""

    @property
    def row_count(self) -> int:
        return len(self.rows)

    def is_empty(self) -> bool:
        return not self.rows or not self.columns


@dataclass(frozen=True, slots=True)
class VerificationResult:
    ok: bool
    plausible: bool
    reason: str | None = None


# --- LLM request/response --------------------------------------------------


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class LLMMessage:
    role: MessageRole
    content: str


@dataclass(frozen=True, slots=True)
class LLMRequest:
    messages: tuple[LLMMessage, ...]
    task: TaskKind
    temperature: float = 0.0
    max_tokens: int | None = None
    stop: tuple[str, ...] = ()
    prompt_version: str | None = None
    stream: bool = False


@dataclass(frozen=True, slots=True)
class LLMResponse:
    text: str
    provider: Provider
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    finish_reason: str | None = None
    cached: bool = False

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


# --- HITL & run bookkeeping ------------------------------------------------


class HITLKind(StrEnum):
    APPROVE_SQL = "approve"
    CLARIFY = "clarify"


@dataclass(frozen=True, slots=True)
class HITLState:
    required: bool = False
    kind: HITLKind = HITLKind.APPROVE_SQL
    decision: HITLDecision | None = None
    edited_sql: str | None = None
    clarification: str | None = None
    options: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RunMeta:
    trace_id: str | None = None
    provider_used: Provider | None = None
    prompt_versions: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentAction:
    """Append-only audit/outbox record of something the agent did (ASI10)."""

    id: str
    run_id: RunId
    action_type: ActionType
    created_at: datetime
    sql_text: str | None = None
    decision: str | None = None
    row_count: int | None = None
    elapsed_ms: int | None = None
    error: str | None = None
