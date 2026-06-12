"""Cache for year-over-year growth-rate calculations, derived from financials."""

from __future__ import annotations

from typing import Any

from backend.services import growth as growth_service

from .base import CacheHelpers
from .financials import FinancialsCache
from .schema import (
    CACHE_CALCULATED,
    CACHE_GROWTH,
    DEPENDENCY_FINANCIALS,
    SUBDOMAIN_BALANCE_SHEET,
    SUBDOMAIN_INCOME_STATEMENT,
)


class GrowthCache:
    CACHE_KEY = CACHE_GROWTH
    BUCKET = CACHE_CALCULATED

    @staticmethod
    def get_or_calculate(
        cache: dict[str, Any],
        ticker: str,
        span: int,
        statement: str,
    ) -> tuple[dict[str, Any], bool]:
        company = CacheHelpers.company(cache, ticker)
        growth_cache = company[CACHE_CALCULATED].setdefault(CACHE_GROWTH, {})
        cached = growth_cache.get(statement)
        if cached and CacheHelpers.coverage_satisfies(cached.get("coverage", {}), span):
            return cached["payload"], True

        hf, _ = FinancialsCache.get_or_fetch(cache, ticker, span)
        if statement == SUBDOMAIN_INCOME_STATEMENT:
            payload = growth_service.get_income_statement_growth_rates(hf)
        elif statement == SUBDOMAIN_BALANCE_SHEET:
            payload = growth_service.get_balance_sheet_growth_rates(hf)
        else:
            raise ValueError(f"Unknown growth statement: {statement}")

        growth_cache[statement] = CacheHelpers.calculated_entry(payload, hf, [DEPENDENCY_FINANCIALS])
        return payload, False

    @staticmethod
    def catalog_entry(company_cache: dict[str, Any]) -> dict | None:
        entry = company_cache.get(CACHE_CALCULATED, {}).get(CACHE_GROWTH, {})
        if not entry:
            return None
        return CacheHelpers.catalog_leaf_map(entry)

    @staticmethod
    def payload_entry(company_cache: dict[str, Any]) -> dict | None:
        entry = company_cache.get(CACHE_CALCULATED, {}).get(CACHE_GROWTH, {})
        if not entry:
            return None
        result = {
            stmt: data["payload"]
            for stmt, data in entry.items()
            if data.get("payload") is not None
        }
        return result or None
