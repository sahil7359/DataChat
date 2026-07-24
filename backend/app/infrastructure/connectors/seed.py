"""Seed connector: the bundled offline slice, so `--dataset seed` needs no
network and no keys (FR-25)."""

from __future__ import annotations

from ingestion.definitions import seed_raw
from ingestion.ports import RawDataset


class SeedConnector:
    name = "seed"

    async def fetch(self) -> RawDataset:
        return seed_raw()
