"""Cache for comparable-company valuations (peer-based and Damodaran fallback)."""

from __future__ import annotations

from typing import Any

from backend.services import comparables as comparables_service

from .base import CacheHelpers
from .schema import (
    CACHE_CALCULATED,
    CACHE_COMPARABLES,
    DEPENDENCY_FINANCIALS,
    DEPENDENCY_MARKET_DATA,
)


class CompsCache:
    CACHE_KEY = CACHE_COMPARABLES
    BUCKET = CACHE_CALCULATED

    @staticmethod
    def get_or_calculate_peer(
        cache: dict[str, Any],
        ticker: str,
        peers: list[str],
    ) -> tuple[dict[str, Any], bool]:
        company = CacheHelpers.company(cache, ticker)
        comps_cache = company[CACHE_CALCULATED].setdefault(CACHE_COMPARABLES, {})
        peer_key = ",".join(sorted(p.strip().upper() for p in peers))
        cached = comps_cache.get("peer")
        if cached and cached.get("peer_key") == peer_key:
            return cached["payload"], True

        payload = comparables_service.peer_comps(cache, ticker, peers)
        comps_cache["peer"] = {
            "payload": payload,
            "peer_key": peer_key,
            "depends_on": [DEPENDENCY_FINANCIALS, DEPENDENCY_MARKET_DATA],
            "last_updated": CacheHelpers.now(),
        }
        return payload, False

    @staticmethod
    def get_or_calculate_damodaran(
        cache: dict[str, Any],
        ticker: str,
    ) -> tuple[dict[str, Any], bool]:
        company = CacheHelpers.company(cache, ticker)
        comps_cache = company[CACHE_CALCULATED].setdefault(CACHE_COMPARABLES, {})
        cached = comps_cache.get("damodaran")
        if cached:
            return cached["payload"], True

        payload = comparables_service.damodaran_fallback(cache, ticker)
        comps_cache["damodaran"] = {
            "payload": payload,
            "depends_on": [DEPENDENCY_FINANCIALS, DEPENDENCY_MARKET_DATA],
            "last_updated": CacheHelpers.now(),
        }
        return payload, False

    @staticmethod
    def catalog_entry(company_cache: dict[str, Any]) -> dict | None:
        entry = company_cache.get(CACHE_CALCULATED, {}).get(CACHE_COMPARABLES, {})
        if not entry:
            return None
        result = {
            key: {"available": True}
            for key in ("peer", "damodaran")
            if entry.get(key)
        }
        return result or None

    @staticmethod
    def payload_entry(company_cache: dict[str, Any]) -> dict | None:
        entry = company_cache.get(CACHE_CALCULATED, {}).get(CACHE_COMPARABLES, {})
        if not entry:
            return None
        result = {
            key: data["payload"]
            for key in ("peer", "damodaran")
            if (data := entry.get(key)) and data.get("payload") is not None
        }
        return result or None
