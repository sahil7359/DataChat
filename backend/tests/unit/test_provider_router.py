import pytest

from app.domain.entities import LLMMessage, LLMRequest, MessageRole
from app.domain.results import AllProvidersUnavailableError
from app.domain.value_objects import Provider, TaskKind
from app.infrastructure.llm.router import ProviderRouter, TaskAwarePolicy
from tests.fakes.llm import FakeLLMProvider


def _req(task: TaskKind) -> LLMRequest:
    return LLMRequest(messages=(LLMMessage(MessageRole.USER, "q"),), task=task)


def _policy() -> TaskAwarePolicy:
    return TaskAwarePolicy(default_order=(Provider.GEMINI, Provider.GROQ))


async def test_falls_back_to_next_provider_on_failure() -> None:
    gemini = FakeLLMProvider(name="gemini", provider=Provider.GEMINI, fail=True)
    groq = FakeLLMProvider(name="groq", provider=Provider.GROQ, default="SELECT 2")
    router = ProviderRouter({Provider.GEMINI: gemini, Provider.GROQ: groq}, _policy())

    resp = await router.complete(_req(TaskKind.SQL_GEN))

    assert resp.provider is Provider.GROQ
    assert resp.text == "SELECT 2"
    assert len(gemini.calls) == 1  # tried first, then fell over


async def test_task_aware_order_prefers_groq_for_short_tasks() -> None:
    gemini = FakeLLMProvider(name="gemini", provider=Provider.GEMINI)
    groq = FakeLLMProvider(name="groq", provider=Provider.GROQ)
    router = ProviderRouter({Provider.GEMINI: gemini, Provider.GROQ: groq}, _policy())

    resp = await router.complete(_req(TaskKind.CLASSIFY))

    assert resp.provider is Provider.GROQ  # groq preferred, so it answers first
    assert len(groq.calls) == 1
    assert len(gemini.calls) == 0


async def test_all_providers_down_raises_single_error() -> None:
    gemini = FakeLLMProvider(name="gemini", fail=True)
    groq = FakeLLMProvider(name="groq", fail=True)
    router = ProviderRouter({Provider.GEMINI: gemini, Provider.GROQ: groq}, _policy())

    with pytest.raises(AllProvidersUnavailableError):
        await router.complete(_req(TaskKind.SQL_GEN))


async def test_adding_a_provider_needs_no_core_change() -> None:
    # OCP: a new provider is just another entry in the map. The router class is
    # untouched; the default policy gives unlisted providers a last-resort turn.
    gemini = FakeLLMProvider(name="gemini", provider=Provider.GEMINI, fail=True)
    groq = FakeLLMProvider(name="groq", provider=Provider.GROQ, fail=True)
    newbie = FakeLLMProvider(name="openrouter", provider=Provider.OPENROUTER, default="SELECT 9")
    router = ProviderRouter(
        {
            Provider.GEMINI: gemini,
            Provider.GROQ: groq,
            Provider.OPENROUTER: newbie,
        },
        _policy(),
    )

    resp = await router.complete(_req(TaskKind.SQL_GEN))
    assert resp.provider is Provider.OPENROUTER
    assert resp.text == "SELECT 9"
