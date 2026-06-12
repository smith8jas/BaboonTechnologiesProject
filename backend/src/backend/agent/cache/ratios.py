"""Cache for financial ratio calculations, derived from financials."""

from __future__ import annotations

from typing import Any

from backend.services import ratio as ratio_service

from .base import CacheHelpers
from .financials import FinancialsCache
from .schema import CACHE_CALCULATED, CACHE_RATIOS, DEPENDENCY_FINANCIALS


class RatiosCache:
    CACHE_KEY = CACHE_RATIOS
    BUCKET = CACHE_CALCULATED

    _RATIO_FUNCS = {
        "liquidity": ratio_service.get_liquidity_ratios,
        "solvency": ratio_service.get_solvency_ratios,
        "profitability": ratio_service.get_profitability_ratios,
        "efficiency": ratio_service.get_efficiency_ratios,
    }

    @staticmethod
    def get_or_calculate(
        cache: dict[str, Any],
        ticker: str,
        span: int,
        ratio_type: str,
    ) -> tuple[dict[str, Any], bool]:
        company = CacheHelpers.company(cache, ticker)
        ratios_cache = company[CACHE_CALCULATED].setdefault(CACHE_RATIOS, {})
        cached = ratios_cache.get(ratio_type)
        if cached and CacheHelpers.coverage_satisfies(cached.get("coverage", {}), span):
            return cached["payload"], True

        hf, _ = FinancialsCache.get_or_fetch(cache, ticker, span)
        payload = RatiosCache._RATIO_FUNCS[ratio_type](hf)
        ratios_cache[ratio_type] = CacheHelpers.calculated_entry(payload, hf, [DEPENDENCY_FINANCIALS])
        return payload, False

    @staticmethod
    def catalog_entry(company_cache: dict[str, Any]) -> dict | None:
        entry = company_cache.get(CACHE_CALCULATED, {}).get(CACHE_RATIOS, {})
        if not entry:
            return None
        return CacheHelpers.catalog_leaf_map(entry)

    @staticmethod
    def payload_entry(company_cache: dict[str, Any]) -> dict | None:
        entry = company_cache.get(CACHE_CALCULATED, {}).get(CACHE_RATIOS, {})
        if not entry:
            return None
        result = {
            ratio_type: data["payload"]
            for ratio_type, data in entry.items()
            if data.get("payload") is not None
        }
        return result or None
