"""BaseNode — Template Method.

``__call__`` fixes the invariant skeleton every node follows: open a trace span →
run the node's own logic → validate its output (LLM output is untrusted, LLM05).
Subclasses implement only ``_run``; they cannot forget to be traced or to have
their output checked. Checkpointing is handled by LangGraph after each super-step.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.agent.state import AgentState
from app.domain.ports.tracing import Tracer

# A node update is a partial AgentState; typed loosely as dict for LangGraph.
NodeUpdate = dict[str, object]


class BaseNode(ABC):
    name: str

    def __init__(self, tracer: Tracer) -> None:
        self._tracer = tracer

    async def __call__(self, state: AgentState) -> NodeUpdate:
        with self._tracer.span(f"node.{self.name}", run_id=state.get("run_id", "")):
            update = await self._run(state)
            self._validate_output(state, update)
            return update

    @abstractmethod
    async def _run(self, state: AgentState) -> NodeUpdate: ...

    def _validate_output(self, state: AgentState, update: NodeUpdate) -> None:
        """Hook: nodes that produce untrusted (LLM) output override this to check
        it before it enters the state. Default is a no-op for pure nodes."""
        return None
