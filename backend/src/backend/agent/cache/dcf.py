"""Cache for DCF valuation scenarios, derived from financials, market, and sector data."""

from __future__ import annotations

from typing import Any

from backend.services import dcf_engine

from .base import CacheHelpers
from .financials import FinancialsCache
from .market_data import MarketDataCache
from .schema import (
    CACHE_CALCULATED,
    CACHE_DCF,
    CACHE_FINANCIALS,
    CACHE_SCENARIOS,
    DEPENDENCY_FINANCIALS,
    DEPENDENCY_MARKET_DATA,
    DEPENDENCY_SECTOR_DATA,
    SCENARIO_DEFAULT,
)
from .sector_data import SectorDataCache


class DCFCache:
    CACHE_KEY = CACHE_DCF
    BUCKET = CACHE_CALCULATED

    @staticmethod
    def get_or_calculate(
        cache: dict[str, Any],
        ticker: str,
        span: int,
        year: int,
    ) -> tuple[dict[str, Any], bool]:
        company = CacheHelpers.company(cache, ticker)
        dcf_cache = company[CACHE_CALCULATED].setdefault(CACHE_DCF, {CACHE_SCENARIOS: {}})
        cached = dcf_cache.setdefault(CACHE_SCENARIOS, {}).get(SCENARIO_DEFAULT)
        if (
            cached
            and CacheHelpers.coverage_satisfies(
                cached.get("source_fingerprint", {}).get(CACHE_FINANCIALS, {}), span
            )
            and cached.get("coverage", {}).get("sector_year") == int(year)
        ):
            return cached["payload"], True

        hf, _ = FinancialsCache.get_or_fetch(cache, ticker, span)
        md, _ = MarketDataCache.get_or_fetch(cache, ticker, True)
        sd, _ = SectorDataCache.get_or_fetch(cache, year)
        assumptions = dcf_engine.build_assumptions(hf, md, sd)
        valuation_inputs = dcf_engine.build_valuation_inputs(hf, md, sd, assumptions)
        result = dcf_engine.run_dcf(hf, valuation_inputs, assumptions)
        payload = CacheHelpers.dump_model(result)
        dcf_cache[CACHE_SCENARIOS][SCENARIO_DEFAULT] = {
            "payload_type": "DCFOutput",
            "payload": payload,
            "coverage": {
                "base_fiscal_year": result.fiscal_year,
                "projection_years": result.projection_years,
                "sector_year": int(year),
            },
            "depends_on": [
                DEPENDENCY_FINANCIALS,
                DEPENDENCY_MARKET_DATA,
                f"{DEPENDENCY_SECTOR_DATA}.{year}",
            ],
            "source_fingerprint": {
                CACHE_FINANCIALS: FinancialsCache.coverage(hf, span),
                "sector_year": int(year),
            },
            "last_updated": CacheHelpers.now(),
        }
        return payload, False

    @staticmethod
    def catalog_entry(company_cache: dict[str, Any]) -> dict | None:
        dcf_entry = (
            company_cache.get(CACHE_CALCULATED, {})
            .get(CACHE_DCF, {})
            .get(CACHE_SCENARIOS, {})
        )
        if not dcf_entry:
            return None
        return {
            scenario: {
                "available": True,
                "base_fiscal_year": data.get("coverage", {}).get("base_fiscal_year"),
                "projection_years": data.get("coverage", {}).get("projection_years", []),
                "intrinsic_value_per_share": (
                    data.get("payload", {}) or {}
                ).get("intrinsic_value_per_share"),
            }
            for scenario, data in dcf_entry.items()
        }

    @staticmethod
    def payload_entry(company_cache: dict[str, Any]) -> dict | None:
        dcf_scenarios = (
            company_cache.get(CACHE_CALCULATED, {})
            .get(CACHE_DCF, {})
            .get(CACHE_SCENARIOS, {})
        )
        if not dcf_scenarios:
            return None
        result = {
            scenario: data["payload"]
            for scenario, data in dcf_scenarios.items()
            if data.get("payload") is not None
        }
        return result or None
