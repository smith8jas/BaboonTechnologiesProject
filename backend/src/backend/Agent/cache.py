"""Agent-local data cache helpers."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import date, datetime, timezone
from typing import Any

from pydantic import BaseModel

from backend.processing.schema import HistoricalFinancials, MarketData, SectorData
from backend.services import dcf_engine, financials, growth, ratio
from .cache_schema import (
    CACHE_CALCULATED,
    CACHE_COMPANIES,
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
    return deepcopy(EMPTY_DATA_CACHE)


def empty_data_catalog() -> dict[str, Any]:
    return deepcopy(EMPTY_DATA_CATALOG)


def build_data_catalog(cache: dict[str, Any]) -> dict[str, Any]:
    catalog = empty_data_catalog()

    for ticker in sorted((cache.get(CACHE_COMPANIES) or {})):
        company = cache[CACHE_COMPANIES][ticker]
        searched = company.get(CACHE_SEARCHED, {})
        calculated = company.get(CACHE_CALCULATED, {})
        entry = {
            "ticker": ticker,
            "name": company.get("name"),
            CACHE_SEARCHED: {},
            CACHE_CALCULATED: {},
        }

        financials_entry = searched.get(CACHE_FINANCIALS)
        if financials_entry:
            coverage = financials_entry.get("coverage", {})
            entry[CACHE_SEARCHED][CACHE_FINANCIALS] = {
                "available": True,
                "fiscal_years": coverage.get("fiscal_years", []),
                "period_ends": coverage.get("period_ends", []),
                "max_span": coverage.get("max_span"),
                "summary": _financials_summary(ticker, coverage),
            }

        market_data_entry = searched.get(CACHE_MARKET_DATA)
        if market_data_entry:
            entry[CACHE_SEARCHED][CACHE_MARKET_DATA] = {
                "available": True,
                "fields": market_data_entry.get("fields", []),
                "include_rfr": market_data_entry.get("include_rfr", False),
                "summary": f"Market data for {ticker} is available.",
            }

        growth_entry = calculated.get(CACHE_GROWTH, {})
        if growth_entry:
            entry[CACHE_CALCULATED][CACHE_GROWTH] = _catalog_leaf_map(growth_entry)

        ratios_entry = calculated.get(CACHE_RATIOS, {})
        if ratios_entry:
            entry[CACHE_CALCULATED][CACHE_RATIOS] = _catalog_leaf_map(ratios_entry)

        dcf_entry = calculated.get(CACHE_DCF, {}).get(CACHE_SCENARIOS, {})
        if dcf_entry:
            entry[CACHE_CALCULATED][CACHE_DCF] = {
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

        catalog[CACHE_COMPANIES].append(entry)

    sector_years = sorted((cache.get(CACHE_GLOBAL, {}).get(CACHE_SECTOR_DATA_BY_YEAR) or {}).keys())
    catalog[CACHE_GLOBAL]["sector_data_years"] = sector_years
    return catalog


def state_cache(state: dict[str, Any]) -> dict[str, Any]:
    cache = deepcopy(state.get("data_cache") or empty_data_cache())
    cache.setdefault(CACHE_COMPANIES, {})
    cache.setdefault(CACHE_GLOBAL, {}).setdefault(CACHE_SECTOR_DATA_BY_YEAR, {})
    return cache


def tool_content(payload: Any) -> str:
    if isinstance(payload, BaseModel):
        return json.dumps(_dump_model(payload), default=str)
    return json.dumps(payload, default=str)


def get_or_fetch_financials(
    cache: dict[str, Any],
    ticker: str,
    span: int = 5,
    fiscal_years: list[int] | None = None,
) -> tuple[HistoricalFinancials, bool]:
    if fiscal_years:
        if _has_fiscal_years(cache, ticker, fiscal_years):
            return _financials_from_cache_by_years(cache, ticker, fiscal_years), True
        needed_span = max(span, date.today().year - min(int(y) for y in fiscal_years) + 2)
        hf = financials.get_cached_financials(_ticker(ticker), int(needed_span))
        _store_financials(cache, hf, int(needed_span))
        return _filter_hf_by_years(hf, fiscal_years), False

    if _has_financials(cache, ticker, span):
        return _financials_from_cache(cache, ticker, span), True

    hf = financials.get_cached_financials(_ticker(ticker), int(span))
    _store_financials(cache, hf, int(span))
    return hf, False


def get_or_fetch_market_data(
    cache: dict[str, Any],
    ticker: str,
    include_rfr: bool = True,
) -> tuple[MarketData, bool]:
    if _has_market_data(cache, ticker, include_rfr):
        return _market_data_from_cache(cache, ticker), True

    md = financials.get_market_data(_ticker(ticker), include_rfr)
    _store_market_data(cache, ticker, md, include_rfr)
    return md, False


def get_or_fetch_sector_data(
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
        "payload": _dump_model(sd),
        "last_updated": _now(),
    }
    return sd, False


def get_or_calculate_growth(
    cache: dict[str, Any],
    ticker: str,
    span: int,
    statement: str,
) -> tuple[dict[str, Any], bool]:
    company = _company(cache, ticker)
    growth_cache = company[CACHE_CALCULATED].setdefault(CACHE_GROWTH, {})
    cached = growth_cache.get(statement)
    if cached and _coverage_satisfies(cached.get("coverage", {}), span):
        return cached["payload"], True

    hf, _ = get_or_fetch_financials(cache, ticker, span)
    if statement == SUBDOMAIN_INCOME_STATEMENT:
        payload = growth.get_income_statement_growth_rates(hf)
    elif statement == SUBDOMAIN_BALANCE_SHEET:
        payload = growth.get_balance_sheet_growth_rates(hf)
    else:
        raise ValueError(f"Unknown growth statement: {statement}")

    growth_cache[statement] = _calculated_entry(payload, hf, [DEPENDENCY_FINANCIALS])
    return payload, False


def get_or_calculate_ratios(
    cache: dict[str, Any],
    ticker: str,
    span: int,
    ratio_type: str,
) -> tuple[dict[str, Any], bool]:
    company = _company(cache, ticker)
    ratios_cache = company[CACHE_CALCULATED].setdefault(CACHE_RATIOS, {})
    cached = ratios_cache.get(ratio_type)
    if cached and _coverage_satisfies(cached.get("coverage", {}), span):
        return cached["payload"], True

    hf, _ = get_or_fetch_financials(cache, ticker, span)
    ratio_funcs = {
        "liquidity": ratio.get_liquidity_ratios,
        "solvency": ratio.get_solvency_ratios,
        "profitability": ratio.get_profitability_ratios,
        "efficiency": ratio.get_efficiency_ratios,
    }
    payload = ratio_funcs[ratio_type](hf)
    ratios_cache[ratio_type] = _calculated_entry(payload, hf, [DEPENDENCY_FINANCIALS])
    return payload, False


def get_or_calculate_dcf(
    cache: dict[str, Any],
    ticker: str,
    span: int,
    year: int,
) -> tuple[dict[str, Any], bool]:
    company = _company(cache, ticker)
    dcf_cache = company[CACHE_CALCULATED].setdefault(CACHE_DCF, {CACHE_SCENARIOS: {}})
    cached = dcf_cache.setdefault(CACHE_SCENARIOS, {}).get(SCENARIO_DEFAULT)
    if (
        cached
        and _coverage_satisfies(cached.get("source_fingerprint", {}).get(CACHE_FINANCIALS, {}), span)
        and cached.get("coverage", {}).get("sector_year") == int(year)
    ):
        return cached["payload"], True

    hf, _ = get_or_fetch_financials(cache, ticker, span)
    md, _ = get_or_fetch_market_data(cache, ticker, True)
    sd, _ = get_or_fetch_sector_data(cache, year)
    assumptions = dcf_engine.build_assumptions(hf, md, sd)
    valuation_inputs = dcf_engine.build_valuation_inputs(hf, md, sd)
    result = dcf_engine.run_dcf(hf, valuation_inputs, assumptions)
    payload = _dump_model(result)
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
            CACHE_FINANCIALS: _financials_coverage(hf, span),
            "sector_year": int(year),
        },
        "last_updated": _now(),
    }
    return payload, False


def _store_financials(cache: dict[str, Any], hf: HistoricalFinancials, span: int) -> None:
    company = _company(cache, hf.ticker)
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
    financials_cache["metadata"] = _dump_model(hf.metadata)
    for period in hf.periods:
        key = period.fiscal_year or period.period_end.isoformat()
        financials_cache["periods_by_fiscal_year"][key] = _dump_model(period)
    financials_cache["coverage"] = _financials_coverage(hf, span)
    financials_cache["last_updated"] = _now()


def _store_market_data(
    cache: dict[str, Any],
    ticker: str,
    md: MarketData,
    include_rfr: bool,
) -> None:
    company = _company(cache, ticker)
    payload_dict = _dump_model(md)
    company[CACHE_SEARCHED][CACHE_MARKET_DATA] = {
        "payload_type": "MarketData",
        "payload": payload_dict,
        "fields": list(payload_dict.keys()),
        "include_rfr": bool(include_rfr),
        "last_updated": _now(),
    }


def _has_financials(cache: dict[str, Any], ticker: str, span: int) -> bool:
    entry = _company(cache, ticker)[CACHE_SEARCHED].get(CACHE_FINANCIALS)
    return bool(entry and _coverage_satisfies(entry.get("coverage", {}), span))


def _has_market_data(cache: dict[str, Any], ticker: str, include_rfr: bool) -> bool:
    entry = _company(cache, ticker)[CACHE_SEARCHED].get(CACHE_MARKET_DATA)
    if not entry:
        return False
    return bool(entry.get("include_rfr")) or not include_rfr


def _financials_from_cache(cache: dict[str, Any], ticker: str, span: int) -> HistoricalFinancials:
    entry = _company(cache, ticker)[CACHE_SEARCHED][CACHE_FINANCIALS]
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
            "ticker": _ticker(ticker),
            "metadata": entry["metadata"],
            "periods": periods,
        }
    )


def _has_fiscal_years(cache: dict[str, Any], ticker: str, fiscal_years: list[int]) -> bool:
    entry = _company(cache, ticker)[CACHE_SEARCHED].get(CACHE_FINANCIALS)
    if not entry:
        return False
    cached = {str(y) for y in entry.get("coverage", {}).get("fiscal_years", [])}
    return all(str(y) in cached for y in fiscal_years)


def _financials_from_cache_by_years(
    cache: dict[str, Any],
    ticker: str,
    fiscal_years: list[int],
) -> HistoricalFinancials:
    entry = _company(cache, ticker)[CACHE_SEARCHED][CACHE_FINANCIALS]
    years_set = {str(y) for y in fiscal_years}
    periods = sorted(
        [v for k, v in entry["periods_by_fiscal_year"].items() if str(k) in years_set],
        key=lambda p: p.get("period_end", ""),
    )
    return HistoricalFinancials.model_validate(
        {"ticker": _ticker(ticker), "metadata": entry["metadata"], "periods": periods}
    )


def _filter_hf_by_years(hf: HistoricalFinancials, fiscal_years: list[int]) -> HistoricalFinancials:
    years_set = {str(y) for y in fiscal_years}
    filtered = [p for p in hf.periods if str(p.fiscal_year) in years_set]
    return HistoricalFinancials.model_validate(
        {
            "ticker": hf.ticker,
            "metadata": hf.metadata.model_dump(mode="json"),
            "periods": [p.model_dump(mode="json") for p in filtered],
        }
    )


def _market_data_from_cache(cache: dict[str, Any], ticker: str) -> MarketData:
    return MarketData.model_validate(_company(cache, ticker)[CACHE_SEARCHED][CACHE_MARKET_DATA]["payload"])


def _company(cache: dict[str, Any], ticker: str) -> dict[str, Any]:
    key = _ticker(ticker)
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


def _calculated_entry(
    payload: dict[str, Any],
    hf: HistoricalFinancials,
    depends_on: list[str],
) -> dict[str, Any]:
    coverage = _financials_coverage(hf, len(hf.periods))
    return {
        "payload": payload,
        "coverage": coverage,
        "depends_on": depends_on,
        "source_fingerprint": {
            CACHE_FINANCIALS: coverage,
        },
        "last_updated": _now(),
    }


def _financials_coverage(hf: HistoricalFinancials, span: int) -> dict[str, Any]:
    return {
        "fiscal_years": [p.fiscal_year for p in hf.periods],
        "period_ends": [p.period_end.isoformat() for p in hf.periods],
        "max_span": max(int(span), len(hf.periods)),
    }


def _coverage_satisfies(coverage: dict[str, Any], span: int) -> bool:
    return int(coverage.get("max_span") or 0) >= int(span)


def _catalog_leaf_map(source: dict[str, Any]) -> dict[str, Any]:
    return {
        key: {
            "available": True,
            "fiscal_years": value.get("coverage", {}).get("fiscal_years", []),
        }
        for key, value in source.items()
    }


def _financials_summary(ticker: str, coverage: dict[str, Any]) -> str:
    years = coverage.get("fiscal_years", [])
    if not years:
        return f"Historical financial statements for {ticker} are available."
    return f"Historical financial statements for {ticker} are available for {years[0]}-{years[-1]}."


def _dump_model(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")


def _ticker(ticker: str) -> str:
    return str(ticker).strip().upper()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
