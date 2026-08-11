"""The golden NL->SQL evaluation set.

Two kinds of case (see ``eval_service``):

- 21 **answerable** cases with gold SQL, scored by result-set equality.
- 5 **refusal** cases with no gold SQL, scored on whether the agent declined
  rather than inventing an answer.

Coverage is deliberate — a set of easy lookups proves nothing. The mix is
lookups, aggregations, rankings, joins/group-by, time-series over the two OWID
years, and out-of-scope refusals.

why: gold SQL carries an explicit LIMIT even where the row count is small, so the
gold query obeys the same MandatoryLimitRule the agent's SQL must satisfy — the
two sides of the comparison then differ only in content, not in shape.

Train/test hygiene: no question here may be a verbatim few-shot example from
``ingestion.definitions``; the retriever puts those examples straight into the
prompt, so a golden question that duplicates one measures copying, not reasoning.
``tests/unit/test_golden_set.py`` enforces this.

Pinned to the ``seed`` dataset (15 countries; WDI 2022; OWID 2021-2022).
Gold SQL runs against that slice, so ``execution_accuracy`` is self-consistent.
"""

from __future__ import annotations

from app.application.services.eval_service import EvalCase

# --- answerable: single-row lookups ----------------------------------------

_LOOKUPS: list[EvalCase] = [
    EvalCase(
        question="What was France's CO2 per capita in 2022?",
        gold_sql=(
            "SELECT co2_per_capita FROM owid_co2 "
            "WHERE country_iso3 = 'FRA' AND year = 2022 LIMIT 1"
        ),
    ),
    EvalCase(
        question="What was Japan's total population in 2022?",
        gold_sql=(
            "SELECT value FROM wdi_values "
            "WHERE country_iso3 = 'JPN' AND indicator_code = 'SP.POP.TOTL' "
            "AND year = 2022 LIMIT 1"
        ),
    ),
    EvalCase(
        question="Which income group is Qatar classified in?",
        gold_sql="SELECT income_group FROM countries WHERE iso3 = 'QAT' LIMIT 1",
    ),
    EvalCase(
        question="Which World Bank region does Brazil belong to?",
        gold_sql="SELECT region FROM countries WHERE iso3 = 'BRA' LIMIT 1",
    ),
]

# --- answerable: aggregations ----------------------------------------------

_AGGREGATIONS: list[EvalCase] = [
    EvalCase(
        question="How many countries are in the dataset?",
        gold_sql="SELECT count(*) AS n FROM countries LIMIT 1",
    ),
    EvalCase(
        question="What is the average life expectancy across all countries in 2022?",
        gold_sql=(
            "SELECT AVG(value) AS avg_life FROM wdi_values "
            "WHERE indicator_code = 'SP.DYN.LE00.IN' AND year = 2022 LIMIT 1"
        ),
    ),
    EvalCase(
        question="What is the combined population of all countries in 2022?",
        gold_sql=(
            "SELECT SUM(value) AS total_population FROM wdi_values "
            "WHERE indicator_code = 'SP.POP.TOTL' AND year = 2022 LIMIT 1"
        ),
    ),
    EvalCase(
        question="What is the highest CO2 per capita recorded in 2022?",
        gold_sql=("SELECT MAX(co2_per_capita) AS max_co2 FROM owid_co2 WHERE year = 2022 LIMIT 1"),
    ),
    EvalCase(
        question="How many countries are classified as high income?",
        gold_sql=("SELECT count(*) AS n FROM countries WHERE income_group = 'High income' LIMIT 1"),
    ),
]

# --- answerable: rankings and multi-country comparisons ---------------------

_RANKINGS: list[EvalCase] = [
    EvalCase(
        question="Which 5 countries had the highest CO2 per capita in 2022?",
        gold_sql=(
            "SELECT country_iso3, co2_per_capita FROM owid_co2 "
            "WHERE year = 2022 ORDER BY co2_per_capita DESC LIMIT 5"
        ),
        notes="Known strict-equality risk: an answer using country names instead of "
        "ISO codes is correct in substance but scores as a miss.",
    ),
    EvalCase(
        question="List the top 3 countries by GDP per capita in 2022.",
        gold_sql=(
            "SELECT c.name, v.value FROM wdi_values v JOIN countries c ON c.iso3 = v.country_iso3 "
            "WHERE v.indicator_code = 'NY.GDP.PCAP.CD' AND v.year = 2022 "
            "ORDER BY v.value DESC LIMIT 3"
        ),
    ),
    EvalCase(
        question="Which 3 countries had the lowest life expectancy in 2022?",
        gold_sql=(
            "SELECT c.name, v.value FROM wdi_values v JOIN countries c ON c.iso3 = v.country_iso3 "
            "WHERE v.indicator_code = 'SP.DYN.LE00.IN' AND v.year = 2022 "
            "ORDER BY v.value ASC LIMIT 3"
        ),
    ),
    EvalCase(
        question="Compare CO2 per capita between the United States and China in 2022.",
        gold_sql=(
            "SELECT country_iso3, co2_per_capita FROM owid_co2 "
            "WHERE country_iso3 IN ('USA', 'CHN') AND year = 2022 LIMIT 10"
        ),
    ),
    EvalCase(
        question="Which country had the largest population in 2022?",
        gold_sql=(
            "SELECT c.name, v.value FROM wdi_values v JOIN countries c ON c.iso3 = v.country_iso3 "
            "WHERE v.indicator_code = 'SP.POP.TOTL' AND v.year = 2022 "
            "ORDER BY v.value DESC LIMIT 1"
        ),
    ),
]

# --- answerable: joins and group-by ----------------------------------------

_JOINS: list[EvalCase] = [
    EvalCase(
        question="What is the average GDP per capita for each World Bank region in 2022?",
        gold_sql=(
            "SELECT c.region, AVG(v.value) AS avg_gdp FROM wdi_values v "
            "JOIN countries c ON c.iso3 = v.country_iso3 "
            "WHERE v.indicator_code = 'NY.GDP.PCAP.CD' AND v.year = 2022 "
            "GROUP BY c.region LIMIT 20"
        ),
    ),
    EvalCase(
        question="Which region had the highest average CO2 per capita in 2022?",
        gold_sql=(
            "SELECT c.region, AVG(o.co2_per_capita) AS avg_co2 FROM owid_co2 o "
            "JOIN countries c ON c.iso3 = o.country_iso3 "
            "WHERE o.year = 2022 GROUP BY c.region ORDER BY avg_co2 DESC LIMIT 1"
        ),
    ),
    EvalCase(
        question="How many countries are in each income group?",
        gold_sql=(
            "SELECT income_group, count(*) AS n FROM countries GROUP BY income_group LIMIT 10"
        ),
    ),
    EvalCase(
        question="What is the average CO2 per capita for upper middle income countries in 2022?",
        gold_sql=(
            "SELECT AVG(o.co2_per_capita) AS avg_co2 FROM owid_co2 o "
            "JOIN countries c ON c.iso3 = o.country_iso3 "
            "WHERE c.income_group = 'Upper middle income' AND o.year = 2022 LIMIT 1"
        ),
    ),
]

# --- answerable: time series (OWID carries 2021 and 2022) -------------------

_TIME_SERIES: list[EvalCase] = [
    EvalCase(
        question="What was the total CO2 emitted across all countries in each year?",
        gold_sql=(
            "SELECT year, SUM(co2) AS total_co2 FROM owid_co2 GROUP BY year ORDER BY year LIMIT 10"
        ),
    ),
    EvalCase(
        question="How much did Qatar's CO2 per capita change between 2021 and 2022?",
        gold_sql=(
            "SELECT MAX(co2_per_capita) FILTER (WHERE year = 2022) "
            "- MAX(co2_per_capita) FILTER (WHERE year = 2021) AS change "
            "FROM owid_co2 WHERE country_iso3 = 'QAT' LIMIT 1"
        ),
    ),
    EvalCase(
        question="Which country had the largest increase in CO2 per capita from 2021 to 2022?",
        gold_sql=(
            "SELECT country_iso3, MAX(co2_per_capita) FILTER (WHERE year = 2022) "
            "- MAX(co2_per_capita) FILTER (WHERE year = 2021) AS increase "
            "FROM owid_co2 GROUP BY country_iso3 ORDER BY increase DESC LIMIT 1"
        ),
    ),
]

# --- refusals: the governed data cannot answer these ------------------------
#
# why: an agent that confidently answers these is worse than one that declines,
# and execution accuracy alone would never catch it.

_REFUSALS: list[EvalCase] = [
    EvalCase(
        question="What was Kenya's CO2 per capita in 2022?",
        expect_refusal=True,
        notes="Out-of-scope country: the seed slice carries 15 countries, not Kenya.",
    ),
    EvalCase(
        question="What is the adult literacy rate in India?",
        expect_refusal=True,
        notes="Out-of-scope indicator: only GDP per capita, population and life expectancy.",
    ),
    EvalCase(
        question="What was the unemployment rate in Germany in 2022?",
        expect_refusal=True,
        notes="Out-of-scope indicator.",
    ),
    EvalCase(
        question="Show me the best countries.",
        expect_refusal=True,
        notes="Ambiguous: 'best' names no metric. Correct behaviour is to ask, not guess.",
    ),
    EvalCase(
        question="What will global CO2 per capita be in 2030?",
        expect_refusal=True,
        notes="Out-of-scope period: the corpus stops at 2022 and holds no forecasts.",
    ),
]

GOLDEN_SET: list[EvalCase] = [
    *_LOOKUPS,
    *_AGGREGATIONS,
    *_RANKINGS,
    *_JOINS,
    *_TIME_SERIES,
    *_REFUSALS,
]
