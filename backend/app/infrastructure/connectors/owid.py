"""Our World in Data CO2 connector.

Parses OWID's published ``owid-co2-data.json`` (keyed by ISO3 with a per-year
``data`` array), keeping only the bounded country allowlist and recent years.
"""

from __future__ import annotations

from typing import Any

import httpx

from ingestion.definitions import _COUNTRIES
from ingestion.ports import RawDataset, TableRows

_URL = "https://nyc3.digitaloceanspaces.com/owid-public/data/co2/owid-co2-data.json"


class OwidConnector:
    name = "owid"

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        url: str = _URL,
        years: tuple[int, ...] = (2021, 2022),
        allowlist: frozenset[str] | None = None,
        timeout_s: float = 60.0,
    ) -> None:
        self._client = client
        self._url = url
        self._years = set(years)
        self._allow = allowlist or frozenset(_COUNTRIES)
        self._timeout = timeout_s

    async def fetch(self) -> RawDataset:
        resp = await self._client.get(self._url, timeout=self._timeout)
        resp.raise_for_status()
        payload: dict[str, Any] = resp.json()

        countries: list[tuple[object, ...]] = []
        co2_rows: list[tuple[object, ...]] = []
        for iso3, record in payload.items():
            if iso3 not in self._allow:
                continue
            countries.append((iso3, record.get("country"), None, None))
            for point in record.get("data", []):
                year = point.get("year")
                if year not in self._years:
                    continue
                co2_rows.append(
                    (
                        iso3,
                        year,
                        point.get("co2"),
                        point.get("co2_per_capita"),
                        point.get("share_global_co2"),
                    )
                )

        tables = (
            TableRows("countries", ("iso3", "name", "region", "income_group"), tuple(countries)),
            TableRows(
                "owid_co2",
                ("country_iso3", "year", "co2", "co2_per_capita", "share_global_co2"),
                tuple(co2_rows),
            ),
        )
        return RawDataset(dataset="owid", source=self._url, tables=tables)
