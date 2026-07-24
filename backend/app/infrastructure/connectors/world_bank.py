"""World Bank WDI connector.

Fetches the country dimension and indicator *values* from the public API. The
indicator metadata (names, units, descriptions) is curated, not fetched, so the
grounding surface can't be poisoned by a changed upstream label. The country set
is deliberately bounded to keep the corpus within the Neon free tier.
"""

from __future__ import annotations

from typing import Any

import httpx

from ingestion.definitions import _COUNTRIES, _INDICATORS
from ingestion.ports import RawDataset, TableRows

_BASE = "https://api.worldbank.org/v2"


class WorldBankConnector:
    name = "wdi"

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        year: int = 2022,
        allowlist: frozenset[str] | None = None,
        timeout_s: float = 30.0,
    ) -> None:
        self._client = client
        self._year = year
        self._allow = allowlist or frozenset(_COUNTRIES)
        self._timeout = timeout_s

    async def fetch(self) -> RawDataset:
        countries = await self._fetch_countries()
        value_rows: list[tuple[object, ...]] = []
        for code, *_ in _INDICATORS:
            value_rows.extend(await self._fetch_indicator(code))
        tables = (
            TableRows("countries", ("iso3", "name", "region", "income_group"), tuple(countries)),
            TableRows(
                "wdi_indicators", ("indicator_code", "name", "unit", "description"), _INDICATORS
            ),
            TableRows(
                "wdi_values",
                ("country_iso3", "indicator_code", "year", "value"),
                tuple(value_rows),
            ),
        )
        return RawDataset(dataset="wdi", source=_BASE, tables=tables)

    async def _get(self, path: str, params: dict[str, str]) -> list[Any]:
        resp = await self._client.get(
            f"{_BASE}/{path}",
            params={"format": "json", "per_page": "400", **params},
            timeout=self._timeout,
        )
        resp.raise_for_status()
        body = resp.json()
        return body if isinstance(body, list) else []

    async def _fetch_countries(self) -> list[tuple[object, ...]]:
        body = await self._get("country/all", {})
        records = body[1] if len(body) > 1 and isinstance(body[1], list) else []
        rows: list[tuple[object, ...]] = []
        for rec in records:
            iso3 = rec.get("id")
            if iso3 not in self._allow:
                continue
            rows.append(
                (
                    iso3,
                    rec.get("name"),
                    (rec.get("region") or {}).get("value"),
                    (rec.get("incomeLevel") or {}).get("value"),
                )
            )
        return rows

    async def _fetch_indicator(self, code: str) -> list[tuple[object, ...]]:
        body = await self._get(f"country/all/indicator/{code}", {"date": str(self._year)})
        records = body[1] if len(body) > 1 and isinstance(body[1], list) else []
        rows: list[tuple[object, ...]] = []
        for rec in records:
            iso3 = rec.get("countryiso3code")
            if iso3 not in self._allow or rec.get("value") is None:
                continue
            rows.append((iso3, code, int(rec["date"]), float(rec["value"])))
        return rows
