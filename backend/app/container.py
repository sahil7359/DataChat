"""Composition root (Factory/DI).

The one place concrete adapters are built and wired to the domain ports. Chooses
mock vs real providers from settings, so the same graph runs keyless locally and
against real vendors in prod. Constructors elsewhere stay dumb; nothing else in
the app knows which concrete classes are in play.
"""

from __future__ import annotations

from typing import Any

import httpx
from langgraph.checkpoint.base import BaseCheckpointSaver

from app.application.agent.graph import GraphBuilder
from app.application.agent.node_factory import NodeDependencies, NodeFactory
from app.application.services.query_service import QueryService
from app.config import Settings
from app.domain.ports.cache import Cache
from app.domain.ports.catalog import SchemaCatalog
from app.domain.ports.llm import EmbeddingProvider, LLMProvider
from app.domain.ports.sql import QueryExecutor
from app.domain.ports.tracing import Tracer
from app.domain.value_objects import Provider
from app.infrastructure.cache.redis_cache import RedisCache
from app.infrastructure.catalog.pgvector import PgVectorSchemaCatalog
from app.infrastructure.db.repositories import (
    SqlAgentActionRepository,
    SqlConversationRepository,
    SqlRunRepository,
)
from app.infrastructure.db.session import (
    create_app_engine,
    create_executor_engine,
    create_session_factory,
)
from app.infrastructure.llm.circuit_breaker import CircuitBreaker
from app.infrastructure.llm.decorators import build_resilient
from app.infrastructure.llm.embeddings import GeminiEmbeddingAdapter, LocalHashEmbeddingProvider
from app.infrastructure.llm.gemini import GeminiAdapter
from app.infrastructure.llm.groq import GroqAdapter
from app.infrastructure.llm.mock import MockLLMProvider
from app.infrastructure.llm.ollama import OllamaAdapter
from app.infrastructure.llm.router import ProviderRouter, TaskAwarePolicy
from app.infrastructure.observability.metrics import Metrics
from app.infrastructure.observability.mlflow_tracer import MLflowTracer
from app.infrastructure.observability.tracing import NullTracer
from app.infrastructure.sql.cache import CachingQueryExecutor
from app.infrastructure.sql.executor import ReadOnlyQueryExecutor
from app.infrastructure.sql.validator import SqlValidatorChain


class Container:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        # MLflow tracing in prod; a no-op tracer under mocks. The tracing
        # *guarantee* comes from BaseNode + the decorator stack, not the backend.
        self._tracer: Tracer = (
            NullTracer() if settings.use_mocks else MLflowTracer(settings.mlflow_tracking_uri)
        )
        self._http = httpx.AsyncClient(timeout=settings.llm_timeout_s)
        self._metrics = Metrics()
        self._cache: Cache = RedisCache.from_url(settings.redis_url)
        self._app_engine = create_app_engine(settings)
        self._sessionmaker = create_session_factory(self._app_engine)
        self._executor_engine = create_executor_engine(settings)

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def cache(self) -> Cache:
        return self._cache

    @property
    def metrics(self) -> Metrics:
        return self._metrics

    def embedder(self) -> EmbeddingProvider:
        key = self._settings.gemini_api_key.get_secret_value()
        if self._settings.use_mocks or not key:
            return LocalHashEmbeddingProvider(dim=self._settings.embedding_dim)
        return GeminiEmbeddingAdapter(
            self._http, key, model=self._settings.embedding_model, dim=self._settings.embedding_dim
        )

    def llm(self) -> LLMProvider:
        if self._settings.use_mocks:
            return MockLLMProvider()
        breaker = CircuitBreaker(
            self._cache,
            fail_threshold=self._settings.breaker_fail_threshold,
            cooldown_s=self._settings.breaker_cooldown_s,
        )
        providers: dict[Provider, LLMProvider] = {}
        if self._settings.ollama_enabled:
            providers[Provider.OLLAMA] = build_resilient(
                OllamaAdapter(
                    self._http,
                    self._settings.ollama_api_key.get_secret_value(),
                    base_url=self._settings.ollama_base_url,
                    model=self._settings.ollama_model,
                    timeout_s=self._settings.llm_timeout_s,
                ),
                tracer=self._tracer,
                cache=self._cache,
                breaker=breaker,
            )
        gemini_key = self._settings.gemini_api_key.get_secret_value()
        if gemini_key:
            providers[Provider.GEMINI] = build_resilient(
                GeminiAdapter(self._http, gemini_key, timeout_s=self._settings.llm_timeout_s),
                tracer=self._tracer,
                cache=self._cache,
                breaker=breaker,
            )
        groq_key = self._settings.groq_api_key.get_secret_value()
        if groq_key:
            providers[Provider.GROQ] = build_resilient(
                GroqAdapter(self._http, groq_key, timeout_s=self._settings.llm_timeout_s),
                tracer=self._tracer,
                cache=self._cache,
                breaker=breaker,
            )
        if not providers:
            return MockLLMProvider()
        return ProviderRouter(providers, TaskAwarePolicy(self._settings.provider_order))

    def catalog(self) -> SchemaCatalog:
        return PgVectorSchemaCatalog(self._sessionmaker, self.embedder())

    def executor(self) -> QueryExecutor:
        inner = ReadOnlyQueryExecutor(
            self._executor_engine,
            row_cap=self._settings.row_cap,
            timeout_s=self._settings.statement_timeout_ms / 1000,
        )
        return CachingQueryExecutor(inner, self._cache, metrics=self._metrics)

    def node_dependencies(self) -> NodeDependencies:
        return NodeDependencies(
            tracer=self._tracer,
            catalog=self.catalog(),
            llm=self.llm(),
            validator=SqlValidatorChain(self._settings.row_cap),
            executor=self.executor(),
            audit=SqlAgentActionRepository(self._sessionmaker),
            retrieval_k=self._settings.retrieval_k,
        )

    def query_service(self, checkpointer: BaseCheckpointSaver[Any] | None = None) -> QueryService:
        factory = NodeFactory(self.node_dependencies())
        graph = GraphBuilder(factory, max_repair_attempts=self._settings.max_repair_attempts).build(
            checkpointer
        )
        return QueryService(
            graph,
            conversations=SqlConversationRepository(self._sessionmaker),
            runs=SqlRunRepository(self._sessionmaker),
        )

    async def aclose(self) -> None:
        await self._http.aclose()
        await self._app_engine.dispose()
        await self._executor_engine.dispose()
