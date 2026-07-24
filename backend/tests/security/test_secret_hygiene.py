"""LLM02 / LLM07 — secrets never leak into reprs, prompts, or the system prompt."""

from __future__ import annotations

import pytest

from app.application.prompts.clarify import _SYSTEM as CLARIFY_SYSTEM
from app.application.prompts.explanation import _SYSTEM as EXPLAIN_SYSTEM
from app.application.prompts.sql_generation import _SYSTEM as SQL_SYSTEM
from app.config import Settings

pytestmark = pytest.mark.security

_SECRET_MARKERS = ("api_key", "apikey", "password", "secret", "bearer", "aiza", "sk-")


def test_secret_keys_are_not_in_settings_repr() -> None:
    settings = Settings(gemini_api_key="super-secret-value")

    assert "super-secret-value" not in repr(settings)
    assert "super-secret-value" not in str(settings.gemini_api_key)
    assert settings.gemini_api_key.get_secret_value() == "super-secret-value"


@pytest.mark.parametrize("prompt", [SQL_SYSTEM, EXPLAIN_SYSTEM, CLARIFY_SYSTEM])
def test_system_prompts_contain_no_secrets(prompt: str) -> None:
    lowered = prompt.lower()
    for marker in _SECRET_MARKERS:
        assert marker not in lowered, f"system prompt mentions '{marker}'"


def test_system_prompt_leakage_reveals_nothing_sensitive() -> None:
    # Even if an attacker extracts the full system prompt (LLM07), it holds no
    # secrets — only the read-only contract and grounding instructions.
    combined = f"{SQL_SYSTEM}\n{EXPLAIN_SYSTEM}\n{CLARIFY_SYSTEM}".lower()
    assert "read-only" in combined
    assert not any(marker in combined for marker in _SECRET_MARKERS)
