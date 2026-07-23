"""The fakes must be drop-in substitutes for the real adapters (Liskov). If a
port's shape changes, these assignments stop type-checking and this test fails."""

from __future__ import annotations

from app.domain.entities import LLMMessage, LLMRequest, MessageRole
from app.domain.ports.cache import Cache
from app.domain.ports.catalog import SchemaCatalog
from app.domain.ports.llm import EmbeddingProvider, LLMProvider
from app.domain.ports.repositories import (
    AgentActionRepository,
    ConversationRepository,
    EvalRepository,
    ExampleRepository,
    RunRepository,
)
from app.domain.ports.sql import QueryExecutor, SqlValidator
from app.domain.ports.tracing import Tracer
from app.domain.value_objects import TaskKind
from tests.fakes.cache import InMemoryCache
from tests.fakes.catalog import FakeSchemaCatalog
from tests.fakes.llm import FakeEmbeddingProvider, FakeLLMProvider
from tests.fakes.repositories import (
    InMemoryAgentActionRepository,
    InMemoryConversationRepository,
    InMemoryEvalRepository,
    InMemoryExampleRepository,
    InMemoryRunRepository,
)
from tests.fakes.sql import FakeQueryExecutor, FakeSqlValidator
from tests.fakes.tracing import NoopTracer


def test_fakes_satisfy_ports_structurally() -> None:
    _llm: LLMProvider = FakeLLMProvider()
    _emb: EmbeddingProvider = FakeEmbeddingProvider()
    _cat: SchemaCatalog = FakeSchemaCatalog()
    _val: SqlValidator = FakeSqlValidator()
    _exec: QueryExecutor = FakeQueryExecutor()
    _cache: Cache = InMemoryCache()
    _tracer: Tracer = NoopTracer()
    _conv: ConversationRepository = InMemoryConversationRepository()
    _run: RunRepository = InMemoryRunRepository()
    _audit: AgentActionRepository = InMemoryAgentActionRepository()
    _ex: ExampleRepository = InMemoryExampleRepository()
    _eval: EvalRepository = InMemoryEvalRepository()
    # runtime_checkable ports also pass an isinstance gate
    assert isinstance(_llm, LLMProvider)
    assert isinstance(_emb, EmbeddingProvider)
    assert _cache and _tracer and _cat and _val and _exec
    assert _conv and _run and _audit and _ex and _eval


async def test_fake_llm_records_calls_and_returns_scripted_text() -> None:
    provider = FakeLLMProvider(responses={TaskKind.SQL_GEN: "SELECT 42"})
    req = LLMRequest(
        messages=(LLMMessage(MessageRole.USER, "count things"),),
        task=TaskKind.SQL_GEN,
    )

    resp = await provider.complete(req)

    assert resp.text == "SELECT 42"
    assert provider.calls == [req]


async def test_fake_embeddings_are_deterministic_and_sized() -> None:
    emb = FakeEmbeddingProvider(dim=768)

    a = await emb.embed("hello")
    b = await emb.embed("hello")
    c = await emb.embed("world")

    assert a.dim == 768
    assert a == b  # deterministic
    assert a != c


async def test_cache_incr_counts() -> None:
    cache = InMemoryCache()
    assert await cache.incr("k", 60) == 1
    assert await cache.incr("k", 60) == 2
