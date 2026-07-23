"""Tracing port. MLflow is the production implementation; a no-op fake is used
in tests. Keeping tracing behind a port means the domain/application code is
instrumented without importing MLflow (Dependency Inversion)."""

from __future__ import annotations

from types import TracebackType
from typing import Protocol


class Span(Protocol):
    def set_attribute(self, key: str, value: object) -> None: ...

    def __enter__(self) -> Span: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None: ...


class Tracer(Protocol):
    def span(self, name: str, **attributes: object) -> Span:
        """Open a span. Nodes wrap their work in one so every step is traced."""
        ...
