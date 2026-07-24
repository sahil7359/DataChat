"""A tiny in-process metrics registry (Prometheus-style).

MLflow holds the deep traces; this is the cheap operational counter surface the
dashboard scrapes (requests, provider failures, breaker state, cache hit-rate).
Deliberately dependency-free — no prometheus_client, no extra service — to stay
$0 and light on the tiny host.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping


def _key(name: str, labels: Mapping[str, str]) -> str:
    if not labels:
        return name
    rendered = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
    return f"{name}{{{rendered}}}"


class Metrics:
    def __init__(self) -> None:
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = {}

    def inc(self, name: str, value: float = 1.0, **labels: str) -> None:
        self._counters[_key(name, labels)] += value

    def set_gauge(self, name: str, value: float, **labels: str) -> None:
        self._gauges[_key(name, labels)] = value

    def snapshot(self) -> dict[str, dict[str, float]]:
        return {"counters": dict(self._counters), "gauges": dict(self._gauges)}

    def cache_hit_rate(self) -> float:
        hits = self._counters.get("cache_hits_total", 0.0)
        misses = self._counters.get("cache_misses_total", 0.0)
        total = hits + misses
        return hits / total if total else 0.0

    def render(self) -> str:
        series = {**self._counters, **self._gauges}
        lines = [f"{key} {value}" for key, value in sorted(series.items())]
        return "\n".join(lines) + "\n" if lines else ""
