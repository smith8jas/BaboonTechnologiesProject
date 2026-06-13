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
from ..cache.session import open_connection
from .base import log_cache_status


@tool
def get_income_statement_growth_rates(
    ticker: str,
    span: int = 5,
    session_id: Annotated[str, InjectedToolArg] = "",
) -> dict:
    """Calculate year-over-year income statement growth rates across the latest span fiscal periods."""
    conn = open_connection(session_id)
    try:
        result, was_cached = GrowthCache.get_or_calculate(conn, ticker, int(span), SUBDOMAIN_INCOME_STATEMENT)
    finally:
        conn.close()
    log_cache_status("get_income_statement_growth_rates", was_cached, ticker=ticker, span=span)
    return {"source": "cache" if was_cached else "external", "data": result}


@tool
def get_balance_sheet_growth_rates(
    ticker: str,
    span: int = 5,
    session_id: Annotated[str, InjectedToolArg] = "",
) -> dict:
    """Calculate year-over-year balance sheet growth rates across the latest span fiscal periods."""
    conn = open_connection(session_id)
    try:
        result, was_cached = GrowthCache.get_or_calculate(conn, ticker, int(span), SUBDOMAIN_BALANCE_SHEET)
    finally:
        conn.close()
    log_cache_status("get_balance_sheet_growth_rates", was_cached, ticker=ticker, span=span)
    return {"source": "cache" if was_cached else "external", "data": result}


@tool
def get_liquidity_ratios(
    ticker: str,
    span: int = 5,
    session_id: Annotated[str, InjectedToolArg] = "",
) -> dict:
    """Calculate liquidity ratios across the latest span fiscal periods."""
    conn = open_connection(session_id)
    try:
        result, was_cached = RatiosCache.get_or_calculate(conn, ticker, int(span), SUBDOMAIN_LIQUIDITY)
    finally:
        conn.close()
    log_cache_status("get_liquidity_ratios", was_cached, ticker=ticker, span=span)
    return {"source": "cache" if was_cached else "external", "data": result}


@tool
def get_solvency_ratios(
    ticker: str,
    span: int = 5,
    session_id: Annotated[str, InjectedToolArg] = "",
) -> dict:
    """Calculate solvency ratios across the latest span fiscal periods."""
    conn = open_connection(session_id)
    try:
        result, was_cached = RatiosCache.get_or_calculate(conn, ticker, int(span), SUBDOMAIN_SOLVENCY)
    finally:
        conn.close()
    log_cache_status("get_solvency_ratios", was_cached, ticker=ticker, span=span)
    return {"source": "cache" if was_cached else "external", "data": result}


@tool
def get_profitability_ratios(
    ticker: str,
    span: int = 5,
    session_id: Annotated[str, InjectedToolArg] = "",
) -> dict:
    """Calculate profitability ratios across the latest span fiscal periods."""
    conn = open_connection(session_id)
    try:
        result, was_cached = RatiosCache.get_or_calculate(conn, ticker, int(span), SUBDOMAIN_PROFITABILITY)
    finally:
        conn.close()
    log_cache_status("get_profitability_ratios", was_cached, ticker=ticker, span=span)
    return {"source": "cache" if was_cached else "external", "data": result}


@tool
def get_efficiency_ratios(
    ticker: str,
    span: int = 5,
    session_id: Annotated[str, InjectedToolArg] = "",
) -> dict:
    """Calculate working capital efficiency ratios across the latest span fiscal periods."""
    conn = open_connection(session_id)
    try:
        result, was_cached = RatiosCache.get_or_calculate(conn, ticker, int(span), SUBDOMAIN_EFFICIENCY)
    finally:
        conn.close()
    log_cache_status("get_efficiency_ratios", was_cached, ticker=ticker, span=span)
    return {"source": "cache" if was_cached else "external", "data": result}


@tool
def run_dcf_valuation(
    ticker: str,
    span: int = 5,
    year: int = 0,
    session_id: Annotated[str, InjectedToolArg] = "",
) -> dict:
    """Run a full DCF valuation for a public company ticker."""
    year = year or date.today().year
    conn = open_connection(session_id)
    try:
        result, was_cached = DCFCache.get_or_calculate(conn, ticker, int(span), int(year))
    finally:
        conn.close()
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
    session_id: Annotated[str, InjectedToolArg] = "",
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
    conn = open_connection(session_id)
    try:
        if peers:
            result, was_cached = CompsCache.get_or_calculate_peer(conn, ticker, peers)
        else:
            result, was_cached = CompsCache.get_or_calculate_damodaran(conn, ticker)
    finally:
        conn.close()
    log_cache_status("get_comps_valuation", was_cached, ticker=ticker)
    return result
