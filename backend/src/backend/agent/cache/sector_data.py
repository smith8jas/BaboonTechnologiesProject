"""Cache for sector-level valuation assumptions keyed by year (global, not per ticker)."""

from __future__ import annotations

from datetime import date
from typing import Any

from backend.processing.schema import SectorData
from backend.services import financials as financials_service

from .base import CacheHelpers
from .schema import CACHE_GLOBAL, CACHE_SECTOR_DATA_BY_YEAR


class SectorDataCache:
    @staticmethod
    def get_or_fetch(
        cache: dict[str, Any],
        year: int | None,
    ) -> tuple[SectorData, bool]:
        resolved_year = str(year or date.today().year)
        cached = cache[CACHE_GLOBAL][CACHE_SECTOR_DATA_BY_YEAR].get(resolved_year)
        if cached:
            return SectorData.model_validate(cached["payload"]), True
        sd = financials_service.get_sector_data(int(resolved_year))
        cache[CACHE_GLOBAL][CACHE_SECTOR_DATA_BY_YEAR][resolved_year] = {
            "payload_type": "SectorData",
            "payload": CacheHelpers.dump_model(sd),
            "last_updated": CacheHelpers.now(),
        }
        return sd, False

    @staticmethod
    def catalog_entry(global_cache: dict[str, Any]) -> list[str]:
        return sorted((global_cache.get(CACHE_SECTOR_DATA_BY_YEAR) or {}).keys())

    @staticmethod
    def payload_entry(global_cache: dict[str, Any]) -> dict | None:
        sector_by_year = (global_cache or {}).get(CACHE_SECTOR_DATA_BY_YEAR) or {}
        data = {
            year: d["payload"]
            for year, d in sector_by_year.items()
            if d.get("payload") is not None
        }
        return data or None
