"""MLflow adapters: the Tracer port, prompt registration, and eval logging.

MLflow is imported lazily and every call is best-effort — observability must never
break the request path. When a tracking server is configured these produce real
traces/metrics; otherwise they degrade to no-ops. This keeps the whole thing $0
and offline-friendly, while the tracing *guarantee* (every node + LLM call is
wrapped in a span) comes from the architecture (BaseNode + the decorator stack),
not from MLflow being up.
"""

from __future__ import annotations

import contextlib
from types import TracebackType
from typing import Any

from app.infrastructure.observability.logging import get_logger

_log = get_logger("mlflow")


class _Span:
    def __init__(self, name: str, attributes: dict[str, object]) -> None:
        self._name = name
        self._attributes = attributes
        self._active: Any = None

    def set_attribute(self, key: str, value: object) -> None:
        if self._active is None:
            return
        with contextlib.suppress(Exception):  # never let tracing raise
            self._active.set_attribute(key, value)

    def __enter__(self) -> _Span:
        try:
            import mlflow

            self._active = mlflow.start_span(name=self._name).__enter__()
            for key, value in self._attributes.items():
                self.set_attribute(key, value)
        except Exception:
            self._active = None
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None:
        if self._active is None:
            return None
        with contextlib.suppress(Exception):
            self._active.__exit__(exc_type, exc, tb)
        return None


class MLflowTracer:
    """Realises the Tracer port over MLflow tracing."""

    def __init__(self, tracking_uri: str | None = None) -> None:
        if tracking_uri:
            try:
                import mlflow

                mlflow.set_tracking_uri(tracking_uri)
            except Exception:
                _log.warning("mlflow_uri_failed")

    def span(self, name: str, **attributes: object) -> _Span:
        return _Span(name, dict(attributes))


def register_prompts(versions: dict[str, str]) -> None:
    """Best-effort registration of prompt versions with MLflow.

    why one batched ``log_params`` rather than a loop of ``log_param``: each call
    round-trips to the tracking server, so N prompts against an unreachable host
    meant N sequential timeouts. Callers must still bound this — see
    ``main._register_prompts_bounded``.
    """
    try:
        import mlflow

        mlflow.log_params({f"prompt.{name}": version for name, version in versions.items()})
    except Exception:
        _log.info("prompt_register_skipped")


def log_eval_metrics(
    execution_accuracy: float, faithfulness: float, guardrail_pass_rate: float, git_sha: str
) -> str | None:
    try:
        import mlflow

        with mlflow.start_run() as run:
            mlflow.log_metrics(
                {
                    "execution_accuracy": execution_accuracy,
                    "faithfulness": faithfulness,
                    "guardrail_pass_rate": guardrail_pass_rate,
                }
            )
            mlflow.set_tag("git_sha", git_sha)
            run_id: str = run.info.run_id
            return run_id
    except Exception:
        _log.info("eval_log_skipped")
        return None
