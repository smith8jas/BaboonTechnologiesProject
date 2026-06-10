"""Agent-local data cache helpers."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import date, datetime, timezone
from typing import Any

from pydantic import BaseModel

from backend.processing.schema import HistoricalFinancials, MarketData, SectorData
from backend.services import dcf_engine, financials, growth, ratio, comparables
from .cache_schema import (
    CACHE_CALCULATED,
    CACHE_COMPANIES,
    CACHE_COMPARABLES,
    CACHE_DCF,
    CACHE_FINANCIALS,
    CACHE_GLOBAL,
    CACHE_GROWTH,
    CACHE_MARKET_DATA,
    CACHE_RATIOS,
    CACHE_SCENARIOS,
    CACHE_SEARCHED,
    CACHE_SECTOR_DATA_BY_YEAR,
    DEPENDENCY_FINANCIALS,
    DEPENDENCY_MARKET_DATA,
    DEPENDENCY_SECTOR_DATA,
    SCENARIO_DEFAULT,
    SUBDOMAIN_BALANCE_SHEET,
    SUBDOMAIN_INCOME_STATEMENT,
)


EMPTY_DATA_CACHE = {
    CACHE_COMPANIES: {},
    CACHE_GLOBAL: {
        CACHE_SECTOR_DATA_BY_YEAR: {},
    },
}

EMPTY_DATA_CATALOG = {
    CACHE_COMPANIES: [],
    CACHE_GLOBAL: {
        "sector_data_years": [],
    },
}


def empty_data_cache() -> dict[str, Any]:
    """Return a fresh mutable cache with the expected top-level keys."""
    return deepcopy(EMPTY_DATA_CACHE)


def empty_data_catalog() -> dict[str, Any]:
    """Return a fresh catalog skeleton used for prompt-visible data summaries."""
    return deepcopy(EMPTY_DATA_CATALOG)


def state_cache(state: dict[str, Any]) -> dict[str, Any]:
    """Return a normalized deep copy of the graph state's data cache."""
    cache = deepcopy(state.get("data_cache") or empty_data_cache())
    cache.setdefault(CACHE_COMPANIES, {})
    cache.setdefault(CACHE_GLOBAL, {}).setdefault(CACHE_SECTOR_DATA_BY_YEAR, {})
    return cache


def tool_content(payload: Any) -> str:
    """Serialize tool payloads into JSON strings for LangChain ToolMessage content."""
    if isinstance(payload, BaseModel):
        return json.dumps(CacheHelpers.dump_model(payload), default=str)
    return json.dumps(payload, default=str)


# ─── Shared utilities ─────────────────────────────────────────────────────────

class CacheHelpers:
    @staticmethod
    def company(cache: dict[str, Any], ticker: str) -> dict[str, Any]:
        key = CacheHelpers.ticker(ticker)
        companies = cache.setdefault(CACHE_COMPANIES, {})
        return companies.setdefault(
            key,
            {
                "ticker": key,
                "name": None,
                CACHE_SEARCHED: {},
                CACHE_CALCULATED: {},
            },
        )

    @staticmethod
    def calculated_entry(
        payload: dict[str, Any],
        hf: HistoricalFinancials,
        depends_on: list[str],
    ) -> dict[str, Any]:
        coverage = FinancialsCache.coverage(hf, len(hf.periods))
        return {
            "payload": payload,
            "coverage": coverage,
            "depends_on": depends_on,
            "source_fingerprint": {CACHE_FINANCIALS: coverage},
            "last_updated": CacheHelpers.now(),
        }

    @staticmethod
    def coverage_satisfies(coverage: dict[str, Any], span: int) -> bool:
        return int(coverage.get("max_span") or 0) >= int(span)

    @staticmethod
    def catalog_leaf_map(source: dict[str, Any]) -> dict[str, Any]:
        return {
            key: {
                "available": True,
                "fiscal_years": value.get("coverage", {}).get("fiscal_years", []),
            }
            for key, value in source.items()
        }

    @staticmethod
    def dump_model(model: BaseModel) -> dict[str, Any]:
        return model.model_dump(mode="json")

    @staticmethod
    def ticker(ticker: str) -> str:
        return str(ticker).strip().upper()

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()


# ─── Tool cache classes ───────────────────────────────────────────────────────

class FinancialsCache:
    CACHE_KEY = CACHE_FINANCIALS
    BUCKET = CACHE_SEARCHED

    @staticmethod
    def get_or_fetch(
        cache: dict[str, Any],
        ticker: str,
        span: int = 5,
        fiscal_years: list[int] | None = None,
    ) -> tuple[HistoricalFinancials, bool]:
        if fiscal_years:
            if FinancialsCache._has_fiscal_years(cache, ticker, fiscal_years):
                return FinancialsCache._from_cache_by_years(cache, ticker, fiscal_years), True
            needed_span = max(span, date.today().year - min(int(y) for y in fiscal_years) + 2)
            hf = financials.get_cached_financials(CacheHelpers.ticker(ticker), int(needed_span))
            FinancialsCache._store(cache, hf, int(needed_span))
            return FinancialsCache._filter_by_years(hf, fiscal_years), False

        if FinancialsCache._has(cache, ticker, span):
            return FinancialsCache._from_cache(cache, ticker, span), True

        hf = financials.get_cached_financials(CacheHelpers.ticker(ticker), int(span))
        FinancialsCache._store(cache, hf, int(span))
        return hf, False

    @staticmethod
    def _store(cache: dict[str, Any], hf: HistoricalFinancials, span: int) -> None:
        company = CacheHelpers.company(cache, hf.ticker)
        company["name"] = hf.metadata.name
        financials_cache = company[CACHE_SEARCHED].setdefault(
            CACHE_FINANCIALS,
            {
                "payload_type": "HistoricalFinancials",
                "metadata": {},
                "periods_by_fiscal_year": {},
                "coverage": {},
                "last_updated": None,
            },
        )
        financials_cache["metadata"] = CacheHelpers.dump_model(hf.metadata)
        for period in hf.periods:
            key = FinancialsCache._fiscal_year_key(period.fiscal_year or period.period_end.year)
            financials_cache["periods_by_fiscal_year"][key] = CacheHelpers.dump_model(period)
        financials_cache["coverage"] = FinancialsCache.coverage(hf, span)
        financials_cache["last_updated"] = CacheHelpers.now()

    @staticmethod
    def _has(cache: dict[str, Any], ticker: str, span: int) -> bool:
        entry = CacheHelpers.company(cache, ticker)[CACHE_SEARCHED].get(CACHE_FINANCIALS)
        return bool(entry and CacheHelpers.coverage_satisfies(entry.get("coverage", {}), span))

    @staticmethod
    def _from_cache(cache: dict[str, Any], ticker: str, span: int) -> HistoricalFinancials:
        entry = CacheHelpers.company(cache, ticker)[CACHE_SEARCHED][CACHE_FINANCIALS]
        periods = [
            value
            for _, value in sorted(
                entry["periods_by_fiscal_year"].items(),
                key=lambda item: item[1].get("period_end", ""),
            )
        ]
        if span:
            periods = periods[-int(span):]
        return HistoricalFinancials.model_validate(
            {
                "ticker": CacheHelpers.ticker(ticker),
                "metadata": entry["metadata"],
                "periods": periods,
            }
        )

    @staticmethod
    def _has_fiscal_years(cache: dict[str, Any], ticker: str, fiscal_years: list[int]) -> bool:
        entry = CacheHelpers.company(cache, ticker)[CACHE_SEARCHED].get(CACHE_FINANCIALS)
        if not entry:
            return False
        cached = {
            FinancialsCache._fiscal_year_key(y)
            for y in entry.get("coverage", {}).get("fiscal_years", [])
        }
        return all(FinancialsCache._fiscal_year_key(y) in cached for y in fiscal_years)

    @staticmethod
    def _from_cache_by_years(
        cache: dict[str, Any],
        ticker: str,
        fiscal_years: list[int],
    ) -> HistoricalFinancials:
        entry = CacheHelpers.company(cache, ticker)[CACHE_SEARCHED][CACHE_FINANCIALS]
        years_set = {FinancialsCache._fiscal_year_key(y) for y in fiscal_years}
        periods = sorted(
            [v for k, v in entry["periods_by_fiscal_year"].items()
             if FinancialsCache._fiscal_year_key(k) in years_set],
            key=lambda p: p.get("period_end", ""),
        )
        return HistoricalFinancials.model_validate(
            {"ticker": CacheHelpers.ticker(ticker), "metadata": entry["metadata"], "periods": periods}
        )

    @staticmethod
    def _filter_by_years(hf: HistoricalFinancials, fiscal_years: list[int]) -> HistoricalFinancials:
        years_set = {FinancialsCache._fiscal_year_key(y) for y in fiscal_years}
        filtered = [p for p in hf.periods if FinancialsCache._fiscal_year_key(p.fiscal_year) in years_set]
        return HistoricalFinancials.model_validate(
            {
                "ticker": hf.ticker,
                "metadata": hf.metadata.model_dump(mode="json"),
                "periods": [p.model_dump(mode="json") for p in filtered],
            }
        )

    @staticmethod
    def coverage(hf: HistoricalFinancials, span: int) -> dict[str, Any]:
        return {
            "fiscal_years": [FinancialsCache._fiscal_year_key(p.fiscal_year) for p in hf.periods],
            "period_ends": [p.period_end.isoformat() for p in hf.periods],
            "max_span": max(int(span), len(hf.periods)),
        }

    @staticmethod
    def _fiscal_year_key(year: Any) -> str:
        return str(year).strip().upper().removeprefix("FY")

    @staticmethod
    def _summary(ticker: str, coverage: dict[str, Any]) -> str:
        years = coverage.get("fiscal_years", [])
        if not years:
            return f"Historical financial statements for {ticker} are available."
        return f"Historical financial statements for {ticker} are available for {years[0]}-{years[-1]}."

    @staticmethod
    def catalog_entry(company_cache: dict[str, Any]) -> dict | None:
        entry = company_cache.get(CACHE_SEARCHED, {}).get(CACHE_FINANCIALS)
        if not entry:
            return None
        coverage = entry.get("coverage", {})
        return {
            "available": True,
            "fiscal_years": coverage.get("fiscal_years", []),
            "period_ends": coverage.get("period_ends", []),
            "max_span": coverage.get("max_span"),
            "summary": FinancialsCache._summary(company_cache.get("ticker", ""), coverage),
        }

    @staticmethod
    def payload_entry(company_cache: dict[str, Any]) -> dict | None:
        entry = company_cache.get(CACHE_SEARCHED, {}).get(CACHE_FINANCIALS)
        if not entry:
            return None
        return {
            "metadata": entry.get("metadata"),
            "periods": sorted(
                entry.get("periods_by_fiscal_year", {}).values(),
                key=lambda p: p.get("period_end", ""),
            ),
        }


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
        md = financials.get_market_data(CacheHelpers.ticker(ticker), include_rfr)
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
        sd = financials.get_sector_data(int(resolved_year))
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
            payload = growth.get_income_statement_growth_rates(hf)
        elif statement == SUBDOMAIN_BALANCE_SHEET:
            payload = growth.get_balance_sheet_growth_rates(hf)
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


class RatiosCache:
    CACHE_KEY = CACHE_RATIOS
    BUCKET = CACHE_CALCULATED

    _RATIO_FUNCS = {
        "liquidity": ratio.get_liquidity_ratios,
        "solvency": ratio.get_solvency_ratios,
        "profitability": ratio.get_profitability_ratios,
        "efficiency": ratio.get_efficiency_ratios,
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
        valuation_inputs = dcf_engine.build_valuation_inputs(hf, md, sd)
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

        payload = comparables.peer_comps(cache, ticker, peers)
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

        payload = comparables.damodaran_fallback(cache, ticker)
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


# ─── Registry ─────────────────────────────────────────────────────────────────

COMPANY_TOOL_CACHES = [
    FinancialsCache,
    MarketDataCache,
    GrowthCache,
    RatiosCache,
    DCFCache,
    CompsCache,
]


# ─── Catalog and payload builders ─────────────────────────────────────────────

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
