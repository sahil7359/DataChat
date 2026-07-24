"""Cosine similarity over embedding tuples (shared by the in-memory catalog)."""

from __future__ import annotations

import math

from app.domain.value_objects import Vector


def cosine(a: Vector, b: Vector) -> float:
    dot = sum(x * y for x, y in zip(a.values, b.values, strict=False))
    na = math.sqrt(sum(x * x for x in a.values))
    nb = math.sqrt(sum(y * y for y in b.values))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)
