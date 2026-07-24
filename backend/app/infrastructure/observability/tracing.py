"""Null tracer — a no-op Tracer used until the MLflow tracer is wired (Phase 10).

Keeping tracing behind the port means nodes are instrumented regardless of
whether a real backend is attached; swapping this for the MLflow tracer is a
one-line change in the composition root.
"""

from __future__ import annotations

from types import TracebackType


class NullSpan:
    def set_attribute(self, key: str, value: object) -> None:
        return None

    def __enter__(self) -> NullSpan:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None:
        return None


class NullTracer:
    def span(self, name: str, **attributes: object) -> NullSpan:
        return NullSpan()
