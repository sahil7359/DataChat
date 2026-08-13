"""Deterministic scope checking for the loaded data slice.

The corpus is deliberately narrow — a fixed set of countries, indicators and
years — so "can this question be answered at all?" is often decidable *without*
asking a model. This module decides it.

why deterministic rather than a prompt instruction: asking the model to decline
is advisory, and it failed exactly where it mattered. A question about 2030
produced ``SUM(co2)/SUM(population) WHERE year = 2030``; over zero matching rows
an aggregate returns **one row containing NULL**, so the pipeline saw row_count=1,
concluded it had data, and answered. A named year outside the loaded range is a
fact we hold, not a judgement call.

alt: keep relying on the model plus an emptiness check (no new code, but the
failure above is invisible and returns a confident non-answer), or ask a second
LLM "is this in scope?" (another call, still probabilistic, still wrong sometimes).

Two things are checked, because two things are reliably decidable:

- **Years.** Any 4-digit year named in the question must be one we loaded.
- **Countries.** Any country named from ISO 3166 that is not in the slice.

Indicators are deliberately *not* checked here. The vocabulary is open — "literacy
rate", "unemployment", "GDP" — so a keyword list would produce false refusals on
phrasings we do support. Those fall through to the model and are caught by the
emptiness check downstream, which is the right order: cheap and certain first,
probabilistic second.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# A four-digit year in a plausible range. Bare numbers like "top 5" or a
# population figure must not be read as years.
_YEAR = re.compile(r"\b(1[89]\d{2}|20\d{2}|21\d{2})\b")


@dataclass(frozen=True, slots=True)
class OutOfScope:
    """Why a question cannot be answered, in terms a user can act on."""

    reason: str
    detail: str


@dataclass(frozen=True, slots=True)
class DataScope:
    """What the loaded slice actually contains.

    Built from the curated dataset definition at composition time, so it cannot
    drift from what was ingested.
    """

    country_names: frozenset[str]  # lowercased, INCLUDING aliases — for matching
    display_names: tuple[str, ...]  # canonical names only — for the message
    country_codes: frozenset[str]  # lowercased ISO3
    years: frozenset[int]
    indicator_labels: tuple[str, ...]  # for the message, not for checking
    known_countries: frozenset[str]  # lowercased ISO-3166 names, for detection

    def check(self, question: str) -> OutOfScope | None:
        """Return why the question is out of scope, or None if it may proceed.

        Conservative by design: it only refuses on something positively
        identified as outside the slice. Anything it cannot decide passes through
        to the normal path.
        """
        lowered = question.lower()

        named_years = {int(y) for y in _YEAR.findall(question)}
        unknown_years = sorted(named_years - self.years)
        if unknown_years and not (named_years & self.years):
            years = ", ".join(str(y) for y in unknown_years)
            return OutOfScope(
                reason="year_out_of_range",
                detail=f"the data does not cover {years}",
            )

        for country in sorted(self.known_countries, key=len, reverse=True):
            if country in self.country_names:
                continue
            if re.search(rf"\b{re.escape(country)}\b", lowered):
                return OutOfScope(
                    reason="country_not_loaded",
                    detail=f"{country.title()} is not one of the loaded countries",
                )
        return None

    def describe(self) -> str:
        """Name the boundary, for the refusal message.

        why the shape matters: an earlier version rendered as
        "15 countries, 2021, 2022", which reads as a three-item list rather than
        a count and a range, and put every measure on one line so the commas
        inside each measure ran together with the commas between them. A refusal
        is only useful if the reader can see the boundary at a glance.
        """
        years = sorted(self.years)
        span = str(years[0]) if len(years) == 1 else f"{years[0]}-{years[-1]}"
        measures = "\n".join(f"  - {label}" for label in self.indicator_labels)
        return (
            f"This demo runs on a deliberately small slice of open data: "
            f"{len(self.display_names)} countries, covering {span}.\n\n"
            f"Countries: {', '.join(self.display_names)}.\n\n"
            f"Measures:\n{measures}"
        )
