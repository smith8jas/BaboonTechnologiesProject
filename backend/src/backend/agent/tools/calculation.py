"""Calculation-phase tools: derive growth, ratios, DCF, and comps from cached data."""

from datetime import date
from typing import Annotated, Optional

from langchain_core.tools import InjectedToolArg, tool

from ..cache import CompsCache, DCFCache, GrowthCache, RatiosCache
from ..cache.schema import (
    SUBDOMAIN_BALANCE_SHEET,
    SUBDOMAIN_EFFICIENCY,
    SUBDOMAIN_INCOME_STATEMENT,
    SUBDOMAIN_LIQUIDITY,
    SUBDOMAIN_PROFITABILITY,
    SUBDOMAIN_SOLVENCY,
)
from .base import log_cache_status, tool_cache


@tool
def get_income_statement_growth_rates(
    ticker: str,
    span: int = 5,
    data_cache: Annotated[dict, InjectedToolArg] = None,
) -> dict:
    """Calculate year-over-year income statement growth rates across the latest span fiscal periods."""
    result, was_cached = GrowthCache.get_or_calculate(
        tool_cache(data_cache),
        ticker,
        int(span),
        SUBDOMAIN_INCOME_STATEMENT,
    )
    log_cache_status("get_income_statement_growth_rates", was_cached, ticker=ticker, span=span)
    return {"source": "cache" if was_cached else "external", "data": result}


@tool
def get_balance_sheet_growth_rates(
    ticker: str,
    span: int = 5,
    data_cache: Annotated[dict, InjectedToolArg] = None,
) -> dict:
    """Calculate year-over-year balance sheet growth rates across the latest span fiscal periods."""
    result, was_cached = GrowthCache.get_or_calculate(
        tool_cache(data_cache),
        ticker,
        int(span),
        SUBDOMAIN_BALANCE_SHEET,
    )
    log_cache_status("get_balance_sheet_growth_rates", was_cached, ticker=ticker, span=span)
    return {"source": "cache" if was_cached else "external", "data": result}


@tool
def get_liquidity_ratios(
    ticker: str,
    span: int = 5,
    data_cache: Annotated[dict, InjectedToolArg] = None,
) -> dict:
    """Calculate liquidity ratios across the latest span fiscal periods."""
    result, was_cached = RatiosCache.get_or_calculate(
        tool_cache(data_cache),
        ticker,
        int(span),
        SUBDOMAIN_LIQUIDITY,
    )
    log_cache_status("get_liquidity_ratios", was_cached, ticker=ticker, span=span)
    return {"source": "cache" if was_cached else "external", "data": result}


@tool
def get_solvency_ratios(
    ticker: str,
    span: int = 5,
    data_cache: Annotated[dict, InjectedToolArg] = None,
) -> dict:
    """Calculate solvency ratios across the latest span fiscal periods."""
    result, was_cached = RatiosCache.get_or_calculate(
        tool_cache(data_cache),
        ticker,
        int(span),
        SUBDOMAIN_SOLVENCY,
    )
    log_cache_status("get_solvency_ratios", was_cached, ticker=ticker, span=span)
    return {"source": "cache" if was_cached else "external", "data": result}


@tool
def get_profitability_ratios(
    ticker: str,
    span: int = 5,
    data_cache: Annotated[dict, InjectedToolArg] = None,
) -> dict:
    """Calculate profitability ratios across the latest span fiscal periods."""
    result, was_cached = RatiosCache.get_or_calculate(
        tool_cache(data_cache),
        ticker,
        int(span),
        SUBDOMAIN_PROFITABILITY,
    )
    log_cache_status("get_profitability_ratios", was_cached, ticker=ticker, span=span)
    return {"source": "cache" if was_cached else "external", "data": result}


@tool
def get_efficiency_ratios(
    ticker: str,
    span: int = 5,
    data_cache: Annotated[dict, InjectedToolArg] = None,
) -> dict:
    """Calculate working capital efficiency ratios across the latest span fiscal periods."""
    result, was_cached = RatiosCache.get_or_calculate(
        tool_cache(data_cache),
        ticker,
        int(span),
        SUBDOMAIN_EFFICIENCY,
    )
    log_cache_status("get_efficiency_ratios", was_cached, ticker=ticker, span=span)
    return {"source": "cache" if was_cached else "external", "data": result}


@tool
def run_dcf_valuation(
    ticker: str,
    span: int = 5,
    year: int = 0,
    data_cache: Annotated[dict, InjectedToolArg] = None,
) -> dict:
    """Run a full DCF valuation for a public company ticker."""
    year = year or date.today().year
    result, was_cached = DCFCache.get_or_calculate(tool_cache(data_cache), ticker, int(span), int(year))
    log_cache_status("run_dcf_valuation", was_cached, ticker=ticker, span=span, year=year)
    return {
        "source": "cache" if was_cached else "external",
        "ticker": ticker,
        "fiscal_year": result.get("fiscal_year"),
        "projection_years": result.get("projection_years"),
        "intrinsic_value_per_share": result.get("intrinsic_value_per_share"),
        "enterprise_value": result.get("enterprise_value"),
        "tv_pct_of_ev": result.get("tv_pct_of_ev"),
    }


@tool
def get_comps_valuation(
    ticker: str,
    peers: Optional[list[str]] = None,
    data_cache: Annotated[dict, InjectedToolArg] = None,
) -> dict:
    """
    Comparable company valuation for a given ticker.

    - With peers: computes P/E, EV/EBITDA, EV/Sales, P/S, P/B against
      the supplied peer tickers and returns an implied equity value band.
    - Without peers: falls back to Damodaran sector median multiples
      (EV/Sales, P/S, Trailing PE) derived from the company's SIC code.

    Always returns a value band, never a single point estimate.
    Does not issue Buy / Hold / Sell recommendations.

    Args:
        ticker: Target company ticker (e.g. "AAPL").
        peers:  Optional list of peer tickers (e.g. ["MSFT", "GOOGL"]).
    """
    cache = tool_cache(data_cache)
    if peers:
        result, was_cached = CompsCache.get_or_calculate_peer(cache, ticker, peers)
    else:
        result, was_cached = CompsCache.get_or_calculate_damodaran(cache, ticker)
    log_cache_status("get_comps_valuation", was_cached, ticker=ticker)
    return result
