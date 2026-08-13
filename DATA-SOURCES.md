# Data sources and attribution

The MIT licence in [LICENSE](./LICENSE) covers **the code in this repository**. It
does not cover the third-party data bundled with it or fetched by it. That data
belongs to its publishers and is used under their terms, credited below.

This file exists because the repository does redistribute a small amount of
third-party data: `backend/ingestion/definitions.py` embeds roughly 90 numeric
values as a bundled fixture so the project runs with no network and no accounts.
Redistribution — even of 90 numbers — deserves an explicit attribution rather than
a link buried in a README table.

## What is bundled

| Source | Used for | Publisher |
|---|---|---|
| **World Development Indicators (WDI)** | GDP per capita, total population, life expectancy at birth — 15 countries, 2022 | [The World Bank](https://data.worldbank.org/) |
| **CO₂ and Greenhouse Gas Emissions** | CO₂ total, per capita and share of global — 15 countries, 2021–2022 | [Our World in Data](https://github.com/owid/co2-data) |
| Country dimension | ISO 3166-1 alpha-3 codes, names, World Bank region and income group | The World Bank |

Both publishers make this data openly available for reuse with attribution. Their
current terms are authoritative and take precedence over anything summarised here:

- World Bank — <https://data.worldbank.org/summary-terms-of-use>
- Our World in Data — <https://ourworldindata.org/about#legal>

## What is fetched, not bundled

`--dataset wdi` calls the World Bank API live
(<https://api.worldbank.org/v2>). `--dataset owid` reads the Our World in Data CO₂
dataset. The bundled `seed` slice exists so neither is required to run the project.

## Accuracy caveat

The bundled figures are approximate real-world 2022 values, rounded, and the 2021
CO₂ series is derived rather than fetched — see the note at the top of
`backend/ingestion/definitions.py`. They are sized for a demo and for a
self-consistent evaluation, **not** for analysis. Anyone wanting real numbers
should take them from the publishers above, and the ingestion connectors in
`backend/app/infrastructure/connectors/` do exactly that.

## Other credits

- The country-name list in `backend/ingestion/iso3166.py` is ISO 3166-1 short
  names, used only to detect out-of-scope questions. It is a validation list; no
  part of it is queryable data.
- Dependency licences are as declared by each package; `pip-audit` and
  `pnpm audit` run in CI.
