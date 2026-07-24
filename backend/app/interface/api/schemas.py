"""API request/response schemas.

Pydantic at the boundary is a security control, not just DX: every field is
length- and type-checked before it reaches the agent (LLM01/LLM05). The question
is bounded so a caller can't push an enormous prompt through the free tiers.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChatOptions(BaseModel):
    approve_sql: bool = False


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = Field(default=None, max_length=64)
    options: ChatOptions = Field(default_factory=ChatOptions)


class ResumeRequest(BaseModel):
    decision: Literal["approve", "edit", "reject"] | None = None
    edited_sql: str | None = Field(default=None, max_length=4000)
    clarification: str | None = Field(default=None, max_length=500)

    def to_command(self) -> dict[str, object]:
        payload: dict[str, object] = {}
        if self.decision is not None:
            payload["decision"] = self.decision
        if self.edited_sql is not None:
            payload["edited_sql"] = self.edited_sql
        if self.clarification is not None:
            payload["clarification"] = self.clarification
        return payload


class DatasetSummary(BaseModel):
    name: str
    source: str
    version: str
    description: str
    tables: list[str]


class TurnResponse(BaseModel):
    role: str
    content: str


class ConversationResponse(BaseModel):
    id: str
    title: str
    turns: list[TurnResponse]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str


class ReadyResponse(BaseModel):
    status: Literal["ready", "degraded"]
    checks: dict[str, bool]


class ErrorResponse(BaseModel):
    code: str
    message: str
    trace_id: str | None = None
