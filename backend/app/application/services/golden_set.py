"""The golden NL->SQL evaluation set (gated in CI).

Questions are distinct from the few-shot examples to avoid train/test leakage.
Gold SQL runs against the seed slice, so ``execution_accuracy`` is self-consistent.
"""

from __future__ import annotations

from app.application.services.eval_service import EvalCase

GOLDEN_SET: list[EvalCase] = [
    EvalCase(
        question="Which 5 countries had the highest CO2 per capita in 2022?",
        gold_sql=(
            "SELECT country_iso3, co2_per_capita FROM owid_co2 "
            "WHERE year = 2022 ORDER BY co2_per_capita DESC LIMIT 5"
        ),
    ),
    EvalCase(
        question="What was Germany's CO2 per capita in 2022?",
        gold_sql="SELECT co2_per_capita FROM owid_co2 WHERE country_iso3 = 'DEU' AND year = 2022",
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
        question="How many countries are in the dataset?",
        gold_sql="SELECT count(*) AS n FROM countries",
    ),
    EvalCase(
        question="What is the average life expectancy across all countries in 2022?",
        gold_sql=(
            "SELECT AVG(value) AS avg_life FROM wdi_values "
            "WHERE indicator_code = 'SP.DYN.LE00.IN' AND year = 2022"
        ),
    ),
]
