"""Cover the runtime mock provider and the offline local embedder — the code
paths that let the whole app run with USE_MOCKS and no keys (FR-25)."""

from __future__ import annotations

from app.domain.entities import LLMMessage, LLMRequest, MessageRole
from app.domain.value_objects import Provider, TaskKind
from app.infrastructure.llm.embeddings import LocalHashEmbeddingProvider
from app.infrastructure.llm.mock import MockLLMProvider
from app.infrastructure.llm.router import ProviderRouter, TaskAwarePolicy
from tests.fakes.llm import FakeLLMProvider


def _req(task: TaskKind) -> LLMRequest:
    return LLMRequest(messages=(LLMMessage(MessageRole.USER, "q"),), task=task)


async def test_mock_returns_seed_compatible_sql() -> None:
    mock = MockLLMProvider()
    resp = await mock.complete(_req(TaskKind.SQL_GEN))
    assert "owid_co2" in resp.text
    assert "LIMIT" in resp.text
    assert resp.provider is Provider.GEMINI


async def test_mock_streams_explanation_tokens() -> None:
    mock = MockLLMProvider()
    tokens = [t async for t in mock.stream(_req(TaskKind.EXPLAIN))]
    assert tokens
    assert "".join(tokens).strip()


async def test_mock_accepts_overrides() -> None:
    mock = MockLLMProvider(responses={TaskKind.SQL_GEN: "SELECT 7"})
    resp = await mock.complete(_req(TaskKind.SQL_GEN))
    assert resp.text == "SELECT 7"


async def test_local_hash_embedding_is_deterministic_and_sized() -> None:
    emb = LocalHashEmbeddingProvider(dim=32)
    a = await emb.embed("carbon")
    b = await emb.embed("carbon")
    c = await emb.embed("gdp")
    assert a.dim == 32
    assert a == b
    assert a != c


async def test_router_streams_from_first_available() -> None:
    groq = FakeLLMProvider(name="groq", provider=Provider.GROQ, default="one two three")
    router = ProviderRouter({Provider.GROQ: groq}, TaskAwarePolicy(default_order=(Provider.GROQ,)))
    tokens = [t async for t in router.stream(_req(TaskKind.EXPLAIN))]
    assert "".join(tokens).split() == ["one", "two", "three"]
