"""The MLflow tracer must degrade to a no-op when MLflow isn't available, so
tracing never breaks the request path (mlflow isn't installed in the core venv)."""

from __future__ import annotations

from app.domain.ports.tracing import Tracer
from app.infrastructure.observability.mlflow_tracer import (
    MLflowTracer,
    log_eval_metrics,
    register_prompts,
)


def test_mlflow_tracer_satisfies_the_port() -> None:
    tracer: Tracer = MLflowTracer()
    assert tracer is not None


def test_span_is_a_safe_context_manager_without_mlflow() -> None:
    tracer = MLflowTracer()
    with tracer.span("node.test", run_id="r1") as span:
        span.set_attribute("k", "v")  # no-op, must not raise


def test_best_effort_helpers_never_raise() -> None:
    register_prompts({"sql_generation": "sql_generation@v1"})
    assert log_eval_metrics(0.8, 0.9, 0.95, "deadbeef") is None  # no server -> None
