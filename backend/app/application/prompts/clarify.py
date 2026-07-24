"""Clarify prompt (versioned). Decides whether a question is ambiguous enough to
ask the user instead of guessing (US3). Kept terse so the classify call is cheap
and easy to route to the fast provider."""

from __future__ import annotations

from app.domain.entities import LLMMessage, MessageRole

CLARIFY_VERSION = "clarify@v1"

_SYSTEM = (
    "You decide if a data question is ambiguous. If it is clear enough to answer "
    "with one query, reply with exactly the word CLEAR. If it is ambiguous, reply "
    "with 2-3 concrete interpretations separated by a pipe character (|), and "
    "nothing else."
)


def build_clarify_messages(question: str) -> tuple[LLMMessage, ...]:
    return (
        LLMMessage(MessageRole.SYSTEM, _SYSTEM),
        LLMMessage(MessageRole.USER, f"Question: {question}"),
    )
