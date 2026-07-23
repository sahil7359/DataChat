"""No-op tracer for tests. Records span names + attributes so tests can assert
instrumentation happened without a real MLflow server."""

from __future__ import annotations

from types import TracebackType


class NoopSpan:
    def __init__(self, name: str, attributes: dict[str, object]) -> None:
        self.name = name
        self.attributes = attributes

    def set_attribute(self, key: str, value: object) -> None:
        self.attributes[key] = value

    def __enter__(self) -> NoopSpan:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None:
        return None


class NoopTracer:
    def __init__(self) -> None:
        self.spans: list[NoopSpan] = []

    def span(self, name: str, **attributes: object) -> NoopSpan:
        span = NoopSpan(name, dict(attributes))
        self.spans.append(span)
        return span
