"""NodeFactory — one place that constructs each node with its dependencies.

Bundling the shared dependencies and building nodes by name keeps the graph
wiring declarative and the constructors dumb (Factory). Adding a node is a new
branch here plus an edge in the builder — nothing else changes.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.application.agent.base_node import BaseNode
from app.application.agent.nodes.execute import ExecuteNode
from app.application.agent.nodes.explain import ExplainNode
from app.application.agent.nodes.generate_sql import GenerateSqlNode
from app.application.agent.nodes.guardrail import GuardrailNode
from app.application.agent.nodes.plan import PlanNode
from app.application.agent.nodes.respond import RespondNode
from app.application.agent.nodes.retrieve import RetrieveContextNode
from app.application.agent.nodes.understand import UnderstandNode
from app.domain.ports.catalog import SchemaCatalog
from app.domain.ports.llm import LLMProvider
from app.domain.ports.sql import QueryExecutor, SqlValidator
from app.domain.ports.tracing import Tracer


@dataclass(frozen=True, slots=True)
class NodeDependencies:
    tracer: Tracer
    catalog: SchemaCatalog
    llm: LLMProvider
    validator: SqlValidator
    executor: QueryExecutor
    retrieval_k: int = 8


class NodeFactory:
    def __init__(self, deps: NodeDependencies) -> None:
        self._deps = deps

    def build(self, name: str) -> BaseNode:
        d = self._deps
        match name:
            case "understand":
                return UnderstandNode(d.tracer)
            case "retrieve":
                return RetrieveContextNode(d.tracer, d.catalog, k=d.retrieval_k)
            case "plan":
                return PlanNode(d.tracer)
            case "generate_sql":
                return GenerateSqlNode(d.tracer, d.llm)
            case "guardrail":
                return GuardrailNode(d.tracer, d.validator)
            case "execute":
                return ExecuteNode(d.tracer, d.executor)
            case "explain":
                return ExplainNode(d.tracer, d.llm)
            case "respond":
                return RespondNode(d.tracer)
            case _:
                raise ValueError(f"unknown node: {name}")
