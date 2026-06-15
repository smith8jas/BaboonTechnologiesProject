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
    """
    Calculate year-over-year income statement growth rates across the latest span fiscal periods.

    Covers revenue, gross profit, EBIT, and net income. All fields are historical
    percentage changes, not forward projections.

    Prerequisites: income statement values for ticker across span periods retrieved via
    get_financials(ticker, span).
    """
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
    """
    Calculate year-over-year balance sheet growth rates across the latest span fiscal periods.

    Covers total assets, equity, debt, and working capital. All fields are historical
    percentage changes, not forward projections.

    Prerequisites: balance sheet values for ticker across span periods retrieved via
    get_financials(ticker, span).
    """
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
    """
    Calculate liquidity ratios (current ratio, quick ratio, cash ratio) across the latest
    span fiscal periods.

    Prerequisites: balance sheet values (current assets, current liabilities, cash) for ticker
    across span periods retrieved via get_financials(ticker, span).
    """
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
    """
    Calculate solvency ratios (debt-to-equity, debt-to-assets, interest coverage) across the
    latest span fiscal periods.

    Prerequisites: income statement (EBIT, interest expense) and balance sheet (total debt,
    total assets, equity) values for ticker across span periods retrieved via
    get_financials(ticker, span).
    """
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
    """
    Calculate profitability ratios (gross profit margin, EBIT margin, net profit margin, ROE,
    ROIC) across the latest span fiscal periods.

    Key output fields:
        roe     Leverage-inflated ROE is structurally different from operationally driven ROE —
                cross-check solvency before concluding.
        roic    Compare to WACC to assess value creation. ROIC below WACC means the business
                is failing to earn its cost of capital regardless of absolute profitability.

    Prerequisites: income statement (revenue, gross profit, EBIT, net income) and balance sheet
    (total assets, equity, invested capital) values for ticker across span periods retrieved via
    get_financials(ticker, span).
    """
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
    """
    Calculate working capital efficiency ratios (DSO, DIO, DPO, CCC) across the latest span
    fiscal periods.

    Key output fields:
        dso   Rising DSO alongside revenue growth may indicate collection deterioration, not
              just growth scale. Check direction of change, not just level.
        dpo   Rising DPO improves CCC mechanically but may strain suppliers — not equivalent
              to improvement via faster collections (falling DSO).
        ccc   Cash conversion cycle = DSO + DIO − DPO. Decompose into drivers before
              concluding.

    Prerequisites: income statement (revenue, COGS) and balance sheet (accounts receivable,
    inventory, accounts payable) values for ticker across span periods retrieved via
    get_financials(ticker, span).
    """
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
    """
    Run a full DCF valuation for a public company ticker.

    Prerequisites:
        - Financial statement values for ticker across span periods retrieved via
          get_financials(ticker, span).
        - Current price, beta, shares outstanding, and risk-free rate retrieved via
          get_market_data(ticker, include_rfr=True).
        - Equity risk premium and terminal growth rate for year retrieved via
          get_sector_data(year).

    Key output fields:
        intrinsic_value_per_share      Model estimate, not a fact. Sensitive to WACC and
                                       terminal growth assumptions — present as a range, not
                                       a precise target.
        tv_pct_of_ev                   Terminal value as % of enterprise value. Values above
                                       70% indicate the valuation is driven by long-run
                                       assumptions, not near-term cash flows, increasing
                                       model sensitivity.
        projected_da                   If all values are zero, depreciation_amortization was
                                       None in the source data. UFCF and enterprise value are
                                       understated — flag this limitation explicitly.
        falled_back_to_risk_free_rate  If true: cost of debt could not be derived from
                                       financial statements and was estimated as risk-free
                                       rate + 150bps. WACC and all downstream valuation
                                       outputs carry additional model risk — state this
                                       explicitly when reporting results.
    """
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
        "wacc": result.get("wacc"),
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
    }


@tool
def get_comps_valuation(
    ticker: str,
    peers: Optional[list[str]] = None,
    session_id: Annotated[str, InjectedToolArg] = "",
) -> dict:
    """
    Comparable company valuation for a given ticker.

    With peers: computes P/E, EV/EBITDA, EV/Sales, P/S, P/B multiples against the supplied
    peer tickers and returns an implied equity value band.
    Prerequisites: financial statement values and current market data for ticker and each peer
    retrieved via get_financials(ticker, span) and get_market_data(ticker) for each.

    Without peers: falls back to Damodaran sector median multiples (EV/Sales, P/S, Trailing PE)
    derived from the company's SIC code.
    Prerequisites: financial statement values and current market data for ticker retrieved via
    get_financials(ticker, span) and get_market_data(ticker).

    Always returns a value band, never a single point estimate. Does not issue Buy / Hold /
    Sell recommendations.

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
