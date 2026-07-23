import uuid

import pytest

from app.domain.results import (
    AllProvidersUnavailableError,
    DataChatError,
    LLMProviderError,
    QuotaExceededError,
)
from app.domain.value_objects import AgentStage, Provider, new_uuid


def test_new_uuid_is_a_valid_unique_uuid() -> None:
    a = new_uuid()
    b = new_uuid()
    assert uuid.UUID(a)  # parses => valid
    assert a != b


def test_enums_serialise_to_stable_strings() -> None:
    assert Provider.GEMINI.value == "gemini"
    assert AgentStage.AWAITING_APPROVAL.value == "awaiting_approval"


def test_llm_provider_error_carries_context() -> None:
    err = LLMProviderError("groq", "429 rate limited", retryable=True)
    assert err.provider == "groq"
    assert err.retryable is True
    assert "groq" in str(err)
    assert isinstance(err, DataChatError)


def test_terminal_exceptions_share_a_base() -> None:
    for exc in (AllProvidersUnavailableError("all down"), QuotaExceededError("quota")):
        assert isinstance(exc, DataChatError)
    with pytest.raises(DataChatError):
        raise QuotaExceededError("boom")
