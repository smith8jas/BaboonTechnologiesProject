"""Cache for current market data (price, beta, shares, market cap) by ticker."""

from __future__ import annotations

from typing import Any

from backend.processing.schema import MarketData
from backend.services import financials as financials_service

from .base import CacheHelpers
from .schema import CACHE_MARKET_DATA, CACHE_SEARCHED


class MarketDataCache:
    CACHE_KEY = CACHE_MARKET_DATA
    BUCKET = CACHE_SEARCHED

    @staticmethod
    def get_or_fetch(
        cache: dict[str, Any],
        ticker: str,
        include_rfr: bool = True,
    ) -> tuple[MarketData, bool]:
        if MarketDataCache._has(cache, ticker, include_rfr):
            return MarketDataCache._from_cache(cache, ticker), True
        md = financials_service.get_market_data(CacheHelpers.ticker(ticker), include_rfr)
        MarketDataCache._store(cache, ticker, md, include_rfr)
        return md, False

    @staticmethod
    def _store(cache: dict[str, Any], ticker: str, md: MarketData, include_rfr: bool) -> None:
        company = CacheHelpers.company(cache, ticker)
        payload_dict = CacheHelpers.dump_model(md)
        company[CACHE_SEARCHED][CACHE_MARKET_DATA] = {
            "payload_type": "MarketData",
            "payload": payload_dict,
            "fields": list(payload_dict.keys()),
            "include_rfr": bool(include_rfr),
            "last_updated": CacheHelpers.now(),
        }

    @staticmethod
    def _has(cache: dict[str, Any], ticker: str, include_rfr: bool) -> bool:
        entry = CacheHelpers.company(cache, ticker)[CACHE_SEARCHED].get(CACHE_MARKET_DATA)
        if not entry:
            return False
        return bool(entry.get("include_rfr")) or not include_rfr

    @staticmethod
    def _from_cache(cache: dict[str, Any], ticker: str) -> MarketData:
        return MarketData.model_validate(
            CacheHelpers.company(cache, ticker)[CACHE_SEARCHED][CACHE_MARKET_DATA]["payload"]
        )

    @staticmethod
    def catalog_entry(company_cache: dict[str, Any]) -> dict | None:
        entry = company_cache.get(CACHE_SEARCHED, {}).get(CACHE_MARKET_DATA)
        if not entry:
            return None
        return {
            "available": True,
            "fields": entry.get("fields", []),
            "include_rfr": entry.get("include_rfr", False),
            "summary": f"Market data for {company_cache.get('ticker', '')} is available.",
        }

    @staticmethod
    def payload_entry(company_cache: dict[str, Any]) -> Any | None:
        entry = company_cache.get(CACHE_SEARCHED, {}).get(CACHE_MARKET_DATA)
        if not entry:
            return None
        return entry.get("payload")
