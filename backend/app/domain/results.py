"""Result/Either types and the domain error taxonomy.

Failure that we expect (invalid SQL, an empty result set, a provider that is
temporarily down) is modelled as data via ``Result`` rather than thrown, so it
shows up in signatures and the caller is forced to handle it. Exceptions are
reserved for the genuinely exceptional — a programming error or a broken
invariant. See Design.md §10.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, NoReturn, TypeVar

T = TypeVar("T")
U = TypeVar("U")
E = TypeVar("E")
F = TypeVar("F")


class ResultError(Exception):
    """Raised only when ``unwrap`` is called on the wrong Result variant."""


@dataclass(frozen=True, slots=True)
class Ok(Generic[T]):
    value: T

    __match_args__ = ("value",)

    def is_ok(self) -> bool:
        return True

    def is_err(self) -> bool:
        return False

    def unwrap(self) -> T:
        return self.value

    def unwrap_or(self, _default: T) -> T:
        return self.value

    def map(self, fn: Callable[[T], U]) -> Ok[U]:
        return Ok(fn(self.value))

    def map_err(self, _fn: Callable[..., object]) -> Ok[T]:
        return self


@dataclass(frozen=True, slots=True)
class Err(Generic[E]):
    error: E

    __match_args__ = ("error",)

    def is_ok(self) -> bool:
        return False

    def is_err(self) -> bool:
        return True

    def unwrap(self) -> NoReturn:
        raise ResultError(f"unwrap() on Err: {self.error!r}")

    def unwrap_or(self, default: T) -> T:
        return default

    def map(self, _fn: Callable[..., object]) -> Err[E]:
        return self

    def map_err(self, fn: Callable[[E], F]) -> Err[F]:
        return Err(fn(self.error))


# A Result is exactly one of Ok or Err. Callers pattern-match on it:
#   match result:
#       case Ok(value): ...
#       case Err(error): ...
type Result[T, E] = Ok[T] | Err[E]


# --- Data-modelled errors (carried inside ``Err``) -------------------------
# These are value objects, not exceptions: they are *returned*, never raised.


@dataclass(frozen=True, slots=True)
class DomainError:
    message: str


@dataclass(frozen=True, slots=True)
class GuardrailError(DomainError):
    """SQL rejected by the validator chain before it could execute (LLM05/LLM06)."""

    rule: str = ""


@dataclass(frozen=True, slots=True)
class ExecutionError(DomainError):
    """The read-only executor could not complete the query (timeout, DB error)."""

    code: str = ""


@dataclass(frozen=True, slots=True)
class RetrievalError(DomainError):
    """The semantic layer could not assemble grounding context."""


@dataclass(frozen=True, slots=True)
class ProviderError(DomainError):
    """An LLM provider call failed after retries/fallback were exhausted."""

    provider: str = ""
    retryable: bool = False


@dataclass(frozen=True, slots=True)
class OutputValidationError(DomainError):
    """Untrusted LLM output failed a boundary/output check (LLM05)."""

    field: str = ""


# --- Exceptions (raised only for the genuinely exceptional) ----------------


class DataChatError(Exception):
    """Base for the rare failures we raise rather than return."""


class LLMProviderError(DataChatError):
    """A single provider call failed. Caught by the router to trigger fallback."""

    def __init__(
        self,
        provider: str,
        message: str,
        *,
        retryable: bool = True,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(f"{provider}: {message}")
        self.provider = provider
        self.retryable = retryable
        self.retry_after = retry_after


class AllProvidersUnavailableError(DataChatError):
    """Every configured provider was exhausted (breakers open / retries spent)."""


class QuotaExceededError(DataChatError):
    """A rate limit or global daily quota was hit (LLM10 bounded consumption)."""
