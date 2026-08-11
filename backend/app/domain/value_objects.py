"""Value objects: small, immutable, identity-free types.

These carry meaning by their value, not an id. Keeping ids as distinct
``NewType`` aliases (rather than bare ``str``) means the type checker stops us
passing a ``RunId`` where a ``ConversationId`` is expected — a cheap correctness
win at the seams.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import NewType

ConversationId = NewType("ConversationId", str)
RunId = NewType("RunId", str)
TurnId = NewType("TurnId", str)
DatasetId = NewType("DatasetId", str)


def new_uuid() -> str:
    return str(uuid.uuid4())


class Provider(StrEnum):
    OLLAMA = "ollama"
    GEMINI = "gemini"
    GROQ = "groq"
    OPENROUTER = "openrouter"


class TaskKind(StrEnum):
    """What an LLM call is for — lets the router pick a provider by strength."""

    SQL_GEN = "sql_gen"
    REPAIR = "repair"
    EXPLAIN = "explain"
    VERIFY = "verify"
    CLARIFY = "clarify"
    CLASSIFY = "classify"
    WEB_ANSWER = "web_answer"
    WEB_TABLE = "web_table"


class RunStatus(StrEnum):
    RUNNING = "running"
    AWAITING_HITL = "awaiting_hitl"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"


class TurnRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ActionType(StrEnum):
    GENERATE_SQL = "generate_sql"
    VALIDATE = "validate"
    EXECUTE = "execute"
    REPAIR = "repair"
    HITL_DECISION = "hitl_decision"


class AgentStage(StrEnum):
    """Node/stage names, surfaced to the UI as SSE ``status`` events."""

    WAKING = "waking"
    UNDERSTAND = "understanding"
    RETRIEVE = "retrieving"
    PLAN = "planning"
    GENERATE_SQL = "generating"
    GUARDRAIL = "validating"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTE = "executing"
    VERIFY = "verifying"
    REPAIR = "repairing"
    EXPLAIN = "explaining"
    VISUALIZE = "visualizing"
    WEB_FALLBACK = "searching_web"
    DONE = "done"


class HITLDecision(StrEnum):
    APPROVE = "approve"
    EDIT = "edit"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class Vector:
    """A dense embedding. Dimension is part of identity (768 for Gemini today)."""

    values: tuple[float, ...]

    @property
    def dim(self) -> int:
        return len(self.values)

    @classmethod
    def of(cls, values: Sequence[float]) -> Vector:
        return cls(tuple(float(v) for v in values))


@dataclass(frozen=True, slots=True)
class ChartSpec:
    """A declarative Vega-Lite spec. Held as data, never as executable code —
    the frontend renders it, so it is validated JSON, not a script (LLM05)."""

    spec: Mapping[str, object]
