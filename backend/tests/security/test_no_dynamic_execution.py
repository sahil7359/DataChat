"""ASI05 — no unexpected code execution. Static guarantee: the codebase contains
no dynamic evaluation (`eval`/`exec`/`compile`) and no shell-outs. SQL runs only
through the guardrail + read-only role; charts are declarative JSON."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.security

_ROOTS = ("app", "ingestion")
_BANNED_CALLS = {"eval", "exec", "compile", "__import__"}


def _python_files() -> list[Path]:
    base = Path(__file__).resolve().parents[2]
    files: list[Path] = []
    for root in _ROOTS:
        files.extend((base / root).rglob("*.py"))
    return files


def test_no_dynamic_evaluation_calls() -> None:
    offenders: list[str] = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in _BANNED_CALLS
            ):
                offenders.append(f"{path.name}:{node.lineno} {node.func.id}")
    assert not offenders, f"dynamic execution found: {offenders}"


def test_no_shell_execution() -> None:
    offenders: list[str] = []
    for path in _python_files():
        source = path.read_text(encoding="utf-8")
        for token in ("os.system(", "subprocess.", "os.popen("):
            if token in source:
                offenders.append(f"{path.name}: {token}")
    assert not offenders, f"shell execution found: {offenders}"
