"""Dataset listing for the UI picker. Served from the curated definitions (no DB
hit) — the semantic summary the frontend needs to show what's queryable."""

from __future__ import annotations

from fastapi import APIRouter

from app.interface.api.schemas import DatasetSummary
from ingestion.definitions import DEFINITIONS

router = APIRouter(tags=["datasets"])


@router.get("/datasets", response_model=list[DatasetSummary])
async def list_datasets() -> list[DatasetSummary]:
    return [
        DatasetSummary(
            name=d.name,
            source=d.source,
            version=d.version,
            description=d.description,
            tables=[t.name for t in d.tables],
        )
        for d in DEFINITIONS.values()
    ]
