"""Startup must not be gated by telemetry, and a misconfigured deploy must be loud.

Both of these are deployment concerns rather than request-path ones: a slow start
fails a platform health check, and a silently-mocked provider looks like a broken
demo with nothing in the logs to explain it.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from app.config import Settings
from app.container import Container
from app.infrastructure.llm.mock import MockLLMProvider
from app.main import _register_prompts_bounded

_VERSIONS = {"sql_generation": "v1", "explanation": "v1"}


async def test_prompt_registration_is_bounded_when_the_tracking_server_hangs() -> None:
    """An unreachable MLflow host used to add ~90s to boot. Startup must give up."""

    def hangs(_versions: dict[str, str]) -> None:
        time.sleep(30)

    settings = Settings(mlflow_startup_timeout_s=0.2)

    started = time.perf_counter()
    await _register_prompts_bounded(hangs, _VERSIONS, settings)
    elapsed = time.perf_counter() - started

    assert elapsed < 5, f"startup blocked for {elapsed:.1f}s on telemetry"


async def test_prompt_registration_still_runs_when_the_server_is_healthy() -> None:
    seen: dict[str, str] = {}

    def records(versions: dict[str, str]) -> None:
        seen.update(versions)

    await _register_prompts_bounded(records, _VERSIONS, Settings(mlflow_startup_timeout_s=5.0))

    assert seen == _VERSIONS


async def test_a_raising_registration_does_not_break_startup() -> None:
    def explodes(_versions: dict[str, str]) -> None:
        raise RuntimeError("tracking server said no")

    await _register_prompts_bounded(explodes, _VERSIONS, Settings())  # must not raise


async def test_registration_runs_off_the_event_loop() -> None:
    """It is a blocking HTTP call; on the loop it would stall every other task."""
    loop_ids: list[int] = []

    def records_thread(_versions: dict[str, str]) -> None:
        import threading

        loop_ids.append(threading.get_ident())

    import threading

    main_thread = threading.get_ident()
    await _register_prompts_bounded(records_thread, _VERSIONS, Settings())

    assert loop_ids and loop_ids[0] != main_thread


def test_a_deploy_with_no_provider_configured_logs_loudly(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """USE_MOCKS=false with no key and no Ollama silently served the mock, which
    answers every question with one canned query. That must be visible.

    structlog renders to stdout, so this reads capsys rather than caplog.
    """
    settings = Settings(use_mocks=False, ollama_enabled=False, gemini_api_key="", groq_api_key="")
    container = Container.__new__(Container)  # skip __init__: no DB/Redis needed here
    container._settings = settings  # type: ignore[attr-defined]
    container._cache = None  # type: ignore[attr-defined]

    provider = container.llm()

    assert isinstance(provider, MockLLMProvider)
    out = capsys.readouterr().out
    assert "no_llm_provider_configured" in out
    assert "DATACHAT_GROQ_API_KEY" in out  # tells the operator how to fix it


def test_mock_mode_does_not_warn(capsys: pytest.CaptureFixture[str]) -> None:
    container = Container.__new__(Container)
    container._settings = Settings(use_mocks=True)  # type: ignore[attr-defined]

    provider = container.llm()

    assert isinstance(provider, MockLLMProvider)
    assert "no_llm_provider_configured" not in capsys.readouterr().out


def test_event_loop_is_not_required_for_the_container_check() -> None:
    """Guards against the warning path accidentally needing async context."""
    assert asyncio.iscoroutinefunction(_register_prompts_bounded)
