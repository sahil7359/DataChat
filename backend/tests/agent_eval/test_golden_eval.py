"""Golden-set evaluation, in two tiers.

**Tier 1 — deterministic pipeline gate (`pytest -m eval`, runs in CI).**
Drives the real graph, real pgvector catalog and real read-only executor, but
with a scripted LLM that returns the gold SQL for each question. Model quality is
held constant on purpose, so the number moves only when the *pipeline* moves:
graph wiring, retrieval, guardrail, execution, or the scorers themselves. It is
free, needs no GPU or keys, and any break drops it off 1.0.

This is explicitly **not** a model-quality gate. With the previous fixed-response
mock the same job scored 0.0 and still passed, because the only assertion was
``0.0 <= execution_accuracy <= 1.0``.

**Tier 2 — real-model quality gate (`pytest -m eval_real`, opt-in).**
Runs the same set against a real provider and compares against the committed
``eval_baseline.json``. Needs a GPU or API keys, so it is skipped unless
``DATACHAT_EVAL_REAL=1``; CI has neither.

why two tiers: the published quality number and the per-PR gate cannot come from
the same run — one needs a real model, the other has to be free and deterministic.
alt: gate CI on a real model (needs paid keys, tolerates flakiness) or publish the
mock number (meaningless). Splitting them keeps both honest.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import Any

import pytest
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.application.agent.graph import GraphBuilder
from app.application.agent.node_factory import NodeDependencies, NodeFactory
from app.application.services.eval_service import EvalService, FaithfulnessJudge
from app.application.services.golden_set import GOLDEN_SET
from app.application.services.query_service import QueryService
from app.config import get_settings
from app.domain.entities import LLMRequest, LLMResponse
from app.domain.value_objects import Provider, TaskKind
from app.infrastructure.catalog.pgvector import PgVectorSchemaCatalog
from app.infrastructure.connectors.seed import SeedConnector
from app.infrastructure.db.ingestion_repositories import (
    PgAnalyticsLoader,
    PgDatasetRegistry,
    PgSemanticLayerRepository,
)
from app.infrastructure.db.repositories import SqlEvalRepository
from app.infrastructure.llm.embeddings import LocalHashEmbeddingProvider
from app.infrastructure.sql.executor import ReadOnlyQueryExecutor
from app.infrastructure.sql.validator import SqlValidatorChain
from ingestion.pipeline import build_pipeline
from tests.fakes.tracing import NoopTracer

pytestmark = [pytest.mark.eval, pytest.mark.integration]

BASELINE_PATH = Path(__file__).resolve().parents[2] / "eval_baseline.json"

# Valid, safe, and matches nothing — the scripted stand-in for "the governed data
# cannot answer this".
_EMPTY_RESULT_SQL = "SELECT co2_per_capita FROM owid_co2 WHERE country_iso3 = 'ZZZ' LIMIT 1"


class GoldScriptedLLM:
    """Returns the gold SQL for whichever golden question the prompt contains.

    Holds model quality constant at 'perfect' so the tier-1 gate measures the
    pipeline around the model rather than the model itself.
    """

    def __init__(self) -> None:
        self.name = "gold-scripted"
        self._by_question = {
            case.question: (_EMPTY_RESULT_SQL if case.expect_refusal else case.gold_sql)
            for case in GOLDEN_SET
        }
        self._static: Mapping[TaskKind, str] = {
            TaskKind.CLARIFY: "CLEAR",
            TaskKind.VERIFY: "1.0",
            TaskKind.CLASSIFY: "in_scope",
            TaskKind.EXPLAIN: "The returned rows answer the question directly.",
        }

    def _sql_for(self, req: LLMRequest) -> str:
        haystack = "\n".join(m.content for m in req.messages)
        # Longest first: one golden question can be a substring of another.
        for question in sorted(self._by_question, key=len, reverse=True):
            if question in haystack:
                return self._by_question[question]
        return _EMPTY_RESULT_SQL

    async def complete(self, req: LLMRequest) -> LLMResponse:
        if req.task in (TaskKind.SQL_GEN, TaskKind.REPAIR):
            text = self._sql_for(req)
        else:
            text = self._static.get(req.task, "OK")
        return LLMResponse(
            text=text,
            provider=Provider.GEMINI,
            model="gold-scripted",
            prompt_tokens=8,
            completion_tokens=len(text.split()),
            finish_reason="stop",
        )

    async def stream(self, req: LLMRequest) -> AsyncIterator[str]:
        response = await self.complete(req)
        yield response.text


def _executor_engine() -> AsyncEngine:
    admin = make_url(os.environ["DATACHAT_TEST_DATABASE_URL"])
    pw = get_settings().executor_role_password.get_secret_value()
    return create_async_engine(admin.set(username="datachat_exec", password=pw))


async def _seed(sessionmaker: async_sessionmaker[AsyncSession], embedder: object) -> None:
    await build_pipeline(
        SeedConnector(),
        loader=PgAnalyticsLoader(sessionmaker),
        registry=PgDatasetRegistry(sessionmaker),
        semantic_repo=PgSemanticLayerRepository(sessionmaker),
        embedder=embedder,  # type: ignore[arg-type]
    ).run("seed")


def _build_harness(
    sessionmaker: async_sessionmaker[AsyncSession],
    embedder: object,
    llm: object,
    engine: AsyncEngine,
) -> EvalService:
    executor = ReadOnlyQueryExecutor(engine, row_cap=1000, timeout_s=5)
    deps = NodeDependencies(
        tracer=NoopTracer(),
        catalog=PgVectorSchemaCatalog(sessionmaker, embedder),  # type: ignore[arg-type]
        llm=llm,  # type: ignore[arg-type]
        validator=SqlValidatorChain(row_cap=1000),
        executor=executor,
    )
    service = QueryService(GraphBuilder(NodeFactory(deps)).build(MemorySaver()))
    return EvalService(service, executor, SqlValidatorChain(1000), FaithfulnessJudge(llm))  # type: ignore[arg-type]


async def test_pipeline_gate_scores_perfectly_with_a_scripted_model(
    migrated_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """With model quality held perfect, anything short of 1.0 is a pipeline break."""
    embedder = LocalHashEmbeddingProvider(dim=768)
    await _seed(migrated_sessionmaker, embedder)

    engine = _executor_engine()
    try:
        harness = _build_harness(migrated_sessionmaker, embedder, GoldScriptedLLM(), engine)
        report = await harness.evaluate(GOLDEN_SET)

        failures = [(r.question, r.failure_reason) for r in report.results if not r.passed]
        assert report.execution_accuracy == 1.0, f"pipeline regression: {failures}"
        assert report.refusal_accuracy == 1.0, f"refusal handling regression: {failures}"
        assert report.sql_valid_rate == 1.0
        assert report.n_answerable + report.n_refusal == len(GOLDEN_SET)

        run_id = await SqlEvalRepository(migrated_sessionmaker).record_run(
            "test-sha", report.execution_accuracy, report.faithfulness, report.sql_valid_rate, None
        )
        assert run_id
    finally:
        await engine.dispose()


def _active_provider(settings: object) -> tuple[str, Any, Any]:
    """Which real provider the quality gate should measure, and its adapter.

    Mirrors ``Container.llm``: a present Ollama leads, otherwise the first cloud
    key that is set. Returns a ``vendor/model`` id used to look up the matching
    baseline, because execution accuracy is as much a property of the model as of
    the pipeline — one blended number across providers would mean nothing.

    why the adapter is wrapped in ``build_resilient`` rather than used raw: a
    26-case run is ~130 back-to-back calls, which a free tier answers with 429.
    A bare adapter turns that into a failed gate that looks like a quality
    regression. Wrapping also makes the measurement representative — it is the
    same stack the deployed app runs, so the number describes the system rather
    than an adapter nobody uses in isolation.
    """
    import httpx

    from app.infrastructure.llm.circuit_breaker import CircuitBreaker
    from app.infrastructure.llm.decorators import build_resilient
    from app.infrastructure.llm.groq import GroqAdapter
    from app.infrastructure.llm.ollama import OllamaAdapter
    from tests.fakes.cache import InMemoryCache

    client = httpx.AsyncClient()

    def _resilient(adapter: Any) -> Any:
        cache = InMemoryCache()
        return build_resilient(
            adapter,
            tracer=NoopTracer(),
            # A high threshold on purpose: rate limiting is expected here and must
            # not trip the breaker into failing the rest of the set.
            breaker=CircuitBreaker(cache, fail_threshold=99, cooldown_s=1),
            cache=cache,
            max_attempts=6,
        )

    if settings.ollama_enabled:  # type: ignore[attr-defined]
        model = settings.ollama_model  # type: ignore[attr-defined]
        ollama = OllamaAdapter(
            client,
            settings.ollama_api_key.get_secret_value(),  # type: ignore[attr-defined]
            base_url=settings.ollama_base_url,  # type: ignore[attr-defined]
            model=model,
            timeout_s=180.0,
        )
        return f"ollama/{model}", _resilient(ollama), client
    groq_key = settings.groq_api_key.get_secret_value()  # type: ignore[attr-defined]
    if groq_key:
        groq = GroqAdapter(client, groq_key, timeout_s=180.0)
        return f"groq/{groq._model}", _resilient(groq), client
    raise pytest.skip("no real provider configured: enable Ollama or set a Groq key")


@pytest.mark.eval_real
@pytest.mark.skipif(
    os.getenv("DATACHAT_EVAL_REAL") != "1",
    reason="set DATACHAT_EVAL_REAL=1 (needs a real provider) to run the quality gate",
)
async def test_real_model_does_not_regress_against_the_committed_baseline(
    migrated_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    document = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    settings = get_settings()
    provider_id, llm, client = _active_provider(settings)

    baselines = document["baselines"]
    if provider_id not in baselines:
        pytest.skip(
            f"no committed baseline for {provider_id!r}. Measure one first, then add it to "
            f"eval_baseline.json. Known: {sorted(baselines)}"
        )
    baseline = baselines[provider_id]

    embedder = LocalHashEmbeddingProvider(dim=768)
    await _seed(migrated_sessionmaker, embedder)

    engine = _executor_engine()
    try:
        harness = _build_harness(migrated_sessionmaker, embedder, llm, engine)
        report = await harness.evaluate(GOLDEN_SET)

        print(
            f"\n[{provider_id}] execution_accuracy={report.execution_accuracy:.4f} "
            f"refusal_accuracy={report.refusal_accuracy:.4f} "
            f"sql_valid_rate={report.sql_valid_rate:.4f} "
            f"faithfulness={report.faithfulness:.4f}"
        )

        tolerance = float(document["regression_tolerance"])
        floor = float(baseline["execution_accuracy"])
        assert not report.regressed(floor, tolerance), (
            f"[{provider_id}] execution_accuracy {report.execution_accuracy:.4f} regressed "
            f"more than {tolerance} below the committed baseline {floor:.4f}"
        )
        assert report.refusal_accuracy >= float(baseline["refusal_accuracy"]) - tolerance
    finally:
        await client.aclose()
        await engine.dispose()
