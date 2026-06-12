"""Catalog and payload builders that summarize the cache for model prompts."""

from __future__ import annotations

from typing import Any

from .base import empty_data_catalog
from .comparables import CompsCache
from .dcf import DCFCache
from .financials import FinancialsCache
from .growth import GrowthCache
from .market_data import MarketDataCache
from .ratios import RatiosCache
from .schema import CACHE_CALCULATED, CACHE_COMPANIES, CACHE_GLOBAL, CACHE_SEARCHED
from .sector_data import SectorDataCache

COMPANY_TOOL_CACHES = [
    FinancialsCache,
    MarketDataCache,
    GrowthCache,
    RatiosCache,
    DCFCache,
    CompsCache,
]


def build_data_catalog(cache: dict[str, Any]) -> dict[str, Any]:
    """Build a compact availability summary for model prompts."""
    catalog = empty_data_catalog()

    for ticker in sorted((cache.get(CACHE_COMPANIES) or {})):
        company = cache[CACHE_COMPANIES][ticker]
        entry = {
            "ticker": ticker,
            "name": company.get("name"),
            CACHE_SEARCHED: {},
            CACHE_CALCULATED: {},
        }
        for tc in COMPANY_TOOL_CACHES:
            result = tc.catalog_entry(company)
            if result is not None:
                entry[tc.BUCKET][tc.CACHE_KEY] = result
        catalog[CACHE_COMPANIES].append(entry)

    catalog[CACHE_GLOBAL]["sector_data_years"] = SectorDataCache.catalog_entry(
        cache.get(CACHE_GLOBAL, {})
    )
    return catalog


def build_data_payload(cache: dict[str, Any]) -> dict[str, Any]:
    """Build the detailed cached data payload used by response generation."""
    payload: dict[str, Any] = {}

    for ticker, company in (cache.get(CACHE_COMPANIES) or {}).items():
        entry: dict[str, Any] = {}
        for tc in COMPANY_TOOL_CACHES:
            result = tc.payload_entry(company)
            if result is not None:
                entry[tc.CACHE_KEY] = result
        if entry:
            payload[ticker] = entry

    sector_data = SectorDataCache.payload_entry(cache.get(CACHE_GLOBAL) or {})
    if sector_data:
        payload["sector_data"] = sector_data

    return payload
