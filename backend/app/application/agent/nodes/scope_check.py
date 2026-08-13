"""Scope-check node: decline out-of-scope questions before spending a model call.

Sits between ``retrieve`` and ``plan``. If the question names a country we did not
load or a year outside the loaded range, the run ends here with a refusal that
states its own boundary.

why here and not later: the previous behaviour asked the model to decline, and it
did so unreliably — "what will global CO2 be in 2030" produced
``SUM(co2)/SUM(population) WHERE year = 2030``, which over zero rows returns one
NULL row, so the pipeline believed it had an answer. It also cost 5+ LLM calls and
the full repair budget to reach that wrong conclusion. A named year outside the
loaded range is a fact, not a judgement, so it is settled deterministically and
for free.

The check is conservative: it refuses only on something positively identified as
outside the slice, and anything undecidable falls through to the normal path.
"""

from __future__ import annotations

from app.application.agent.base_node import BaseNode, NodeUpdate
from app.application.agent.state import AgentState
from app.domain.ports.tracing import Tracer
from app.domain.scope import DataScope
from app.domain.value_objects import AgentStage

OUT_OF_SCOPE_CODE = "out_of_scope"


class ScopeCheckNode(BaseNode):
    name = "scope_check"

    def __init__(self, tracer: Tracer, scope: DataScope, *, example: str) -> None:
        super().__init__(tracer)
        self._scope = scope
        self._example = example

    async def _run(self, state: AgentState) -> NodeUpdate:
        verdict = self._scope.check(state["question"])
        if verdict is None:
            return {"stage": AgentStage.RETRIEVE.value}
        # Surfaced as `explanation`, not as an error: declining a question we
        # genuinely cannot answer is the system working, and rendering it in the
        # UI's error styling would make a correct guardrail look like a crash.
        # `error_code` is still set so telemetry and the eval can count refusals.
        return {
            "explanation": self._message(verdict.detail),
            "error_code": OUT_OF_SCOPE_CODE,
            "stage": AgentStage.DONE.value,
        }

    def _message(self, detail: str) -> str:
        """Name the boundary and give a question that works.

        why not a bare "I can't answer that": a refusal that states its scope
        reads as a deliberate design decision; one that does not reads as broken.
        The user should be able to ask a good question on their next try without
        guessing.
        """
        return (
            f"I can't answer that — {detail}.\n\n"
            f"{self._scope.describe()}\n\n"
            f'Try: "{self._example}"'
        )
