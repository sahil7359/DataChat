from app.infrastructure.llm.circuit_breaker import BreakerState, CircuitBreaker
from tests.fakes.cache import InMemoryCache


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def _breaker(clock: FakeClock, *, threshold: int = 3, cooldown: int = 30) -> CircuitBreaker:
    return CircuitBreaker(
        InMemoryCache(), fail_threshold=threshold, cooldown_s=cooldown, clock=clock
    )


async def test_starts_closed_and_allows() -> None:
    cb = _breaker(FakeClock())
    assert await cb.allow("gemini")
    assert await cb.state("gemini") is BreakerState.CLOSED


async def test_opens_after_threshold_failures() -> None:
    clock = FakeClock()
    cb = _breaker(clock, threshold=3)

    for _ in range(3):
        await cb.record_failure("gemini")

    assert await cb.state("gemini") is BreakerState.OPEN
    assert not await cb.allow("gemini")  # still within cooldown


async def test_half_opens_after_cooldown_then_closes_on_success() -> None:
    clock = FakeClock()
    cb = _breaker(clock, threshold=2, cooldown=30)

    await cb.record_failure("gemini")
    await cb.record_failure("gemini")
    assert await cb.state("gemini") is BreakerState.OPEN

    clock.advance(31)
    assert await cb.allow("gemini")  # probe permitted
    assert await cb.state("gemini") is BreakerState.HALF_OPEN

    await cb.record_success("gemini")
    assert await cb.state("gemini") is BreakerState.CLOSED
    assert await cb.allow("gemini")


async def test_half_open_probe_failure_reopens_immediately() -> None:
    clock = FakeClock()
    cb = _breaker(clock, threshold=2, cooldown=30)

    await cb.record_failure("gemini")
    await cb.record_failure("gemini")
    clock.advance(31)
    await cb.allow("gemini")  # -> HALF_OPEN

    await cb.record_failure("gemini")  # a single probe failure re-opens
    assert await cb.state("gemini") is BreakerState.OPEN


async def test_breakers_are_independent_per_provider() -> None:
    cb = _breaker(FakeClock(), threshold=1)
    await cb.record_failure("gemini")
    assert await cb.state("gemini") is BreakerState.OPEN
    assert await cb.state("groq") is BreakerState.CLOSED
