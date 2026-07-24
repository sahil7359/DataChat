"""Connector parsers via httpx.MockTransport — real parsing, no network."""

from __future__ import annotations

from collections.abc import Callable

import httpx

from app.infrastructure.connectors.owid import OwidConnector
from app.infrastructure.connectors.world_bank import WorldBankConnector

Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_world_bank_parses_countries_and_values() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/country/all"):
            return httpx.Response(
                200,
                json=[
                    {"page": 1},
                    [
                        {
                            "id": "USA",
                            "name": "United States",
                            "region": {"value": "North America"},
                            "incomeLevel": {"value": "High income"},
                        },
                        {"id": "ZZZ", "name": "Aggregate", "region": {"value": "Agg"}},
                    ],
                ],
            )
        return httpx.Response(
            200,
            json=[
                {"page": 1},
                [
                    {"countryiso3code": "USA", "date": "2022", "value": 76329.0},
                    {"countryiso3code": "USA", "date": "2022", "value": None},  # dropped
                    {"countryiso3code": "ZZZ", "date": "2022", "value": 1.0},  # off-allowlist
                ],
            ],
        )

    async with _client(handler) as client:
        connector = WorldBankConnector(client, allowlist=frozenset({"USA"}))
        raw = await connector.fetch()

    by_name = {t.name: t for t in raw.tables}
    assert by_name["countries"].rows == (("USA", "United States", "North America", "High income"),)
    # 3 indicators requested, each yields one valid USA row.
    assert len(by_name["wdi_values"].rows) == 3
    assert all(r[0] == "USA" for r in by_name["wdi_values"].rows)


async def test_owid_parses_selected_years_and_countries() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "USA": {
                    "country": "United States",
                    "data": [
                        {
                            "year": 2020,
                            "co2": 4700.0,
                            "co2_per_capita": 14.0,
                            "share_global_co2": 0.13,
                        },
                        {
                            "year": 2022,
                            "co2": 4900.0,
                            "co2_per_capita": 14.9,
                            "share_global_co2": 0.13,
                        },
                    ],
                },
                "ZZZ": {"country": "Nowhere", "data": [{"year": 2022, "co2": 1.0}]},
            },
        )

    async with _client(handler) as client:
        connector = OwidConnector(client, years=(2022,), allowlist=frozenset({"USA"}))
        raw = await connector.fetch()

    co2 = next(t for t in raw.tables if t.name == "owid_co2")
    assert co2.rows == (("USA", 2022, 4900.0, 14.9, 0.13),)
