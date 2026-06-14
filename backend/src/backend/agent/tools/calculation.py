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
        result, was_cached = GrowthCache.get_or_calculate(conn, ticker, int(span), SUBDOMAIN_INCOME_STATEMENT, session_id=session_id)
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
        result, was_cached = GrowthCache.get_or_calculate(conn, ticker, int(span), SUBDOMAIN_BALANCE_SHEET, session_id=session_id)
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
        result, was_cached = RatiosCache.get_or_calculate(conn, ticker, int(span), SUBDOMAIN_LIQUIDITY, session_id=session_id)
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
        result, was_cached = RatiosCache.get_or_calculate(conn, ticker, int(span), SUBDOMAIN_SOLVENCY, session_id=session_id)
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
        result, was_cached = RatiosCache.get_or_calculate(conn, ticker, int(span), SUBDOMAIN_PROFITABILITY, session_id=session_id)
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
        result, was_cached = RatiosCache.get_or_calculate(conn, ticker, int(span), SUBDOMAIN_EFFICIENCY, session_id=session_id)
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
        result, was_cached = DCFCache.get_or_calculate(conn, ticker, int(span), int(year), session_id=session_id)
    finally:
        conn.close()
    log_cache_status("run_dcf_valuation", was_cached, ticker=ticker, span=span, year=year)
    return {
        "source": "cache" if was_cached else "external",
        "ticker": ticker,
        "fiscal_year": result.get("fiscal_year"),
        "projection_years": result.get("projection_years"),
        "projected_revenue": result.get("projected_revenue"),
        "projected_ebit": result.get("projected_ebit"),
        "projected_ebiat": result.get("projected_ebiat"),
        "projected_da": result.get("projected_da"),
        "projected_capex": result.get("projected_capex"),
        "projected_delta_nwc": result.get("projected_delta_nwc"),
        "projected_fcff": result.get("projected_fcff"),
        "pv_fcff": result.get("pv_fcff"),
        "pv_factors": result.get("pv_factors"),
        "terminal_value": result.get("terminal_value"),
        "pv_terminal": result.get("pv_terminal"),
        "enterprise_value": result.get("enterprise_value"),
        "tv_pct_of_ev": result.get("tv_pct_of_ev"),
        "equity_value": result.get("equity_value"),
        "intrinsic_value_per_share": result.get("intrinsic_value_per_share"),
        "falled_back_to_risk_free_rate": result.get("falled_back_to_risk_free_rate"),
        "wacc": result.get("wacc"),               # ← still need to add these
        "terminal_growth": result.get("terminal_growth"),
        "wacc_components": {
            "cost_of_equity": result.get("cost_of_equity"),
            "cost_of_debt_after_tax": result.get("cost_of_debt_after_tax"),
            "risk_free_rate": result.get("risk_free_rate"),
            "equity_risk_premium": result.get("equity_risk_premium"),
            "beta": result.get("beta"),
            "tax_rate": result.get("tax_rate"),
            "equity_weight": result.get("equity_weight"),
            "debt_weight": result.get("debt_weight"),
        },
        "terminal_growth": result.get("terminal_growth"),
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
            result, was_cached = CompsCache.get_or_calculate_peer(conn, ticker, peers, session_id=session_id)
        else:
            result, was_cached = CompsCache.get_or_calculate_damodaran(conn, ticker, session_id=session_id)
    finally:
        conn.close()
    log_cache_status("get_comps_valuation", was_cached, ticker=ticker)
    return result
