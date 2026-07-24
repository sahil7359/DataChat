from app.domain.entities import ExecutionResult
from app.domain.results import Err, ExecutionError, Ok, Result
from app.infrastructure.sql.cache import CachingQueryExecutor
from tests.fakes.cache import InMemoryCache


class CountingExecutor:
    def __init__(self, result: Result[ExecutionResult, ExecutionError]) -> None:
        self._result = result
        self.calls = 0

    async def execute(self, sql: str) -> Result[ExecutionResult, ExecutionError]:
        self.calls += 1
        return self._result


def _rows() -> ExecutionResult:
    return ExecutionResult(columns=("n",), rows=((1,),), row_count=1, elapsed_ms=2)


async def test_identical_sql_is_served_from_cache() -> None:
    inner = CountingExecutor(Ok(_rows()))
    executor = CachingQueryExecutor(inner, InMemoryCache())

    first = await executor.execute("SELECT 1 LIMIT 1")
    second = await executor.execute("SELECT 1 LIMIT 1")

    assert inner.calls == 1  # second hit the cache
    assert isinstance(first, Ok)
    assert isinstance(second, Ok)
    assert second.value.columns == ("n",)


async def test_errors_are_not_cached() -> None:
    inner = CountingExecutor(Err(ExecutionError("boom", code="db_error")))
    executor = CachingQueryExecutor(inner, InMemoryCache())

    await executor.execute("SELECT bad LIMIT 1")
    await executor.execute("SELECT bad LIMIT 1")

    assert inner.calls == 2  # failures always re-run


async def test_different_sql_uses_different_keys() -> None:
    inner = CountingExecutor(Ok(_rows()))
    executor = CachingQueryExecutor(inner, InMemoryCache())

    await executor.execute("SELECT 1 LIMIT 1")
    await executor.execute("SELECT 2 LIMIT 1")

    assert inner.calls == 2
