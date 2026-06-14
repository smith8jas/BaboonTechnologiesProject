"""Research-phase tools: pull external data (financials, market, sector, web)."""

from typing import Annotated

from langchain_core.tools import InjectedToolArg, tool

from backend.services.scrape import search_and_scrape

from ..cache import FinancialsCache, MarketDataCache, SectorDataCache
from ..cache.session import open_connection
from .base import log_cache_status


@tool
def get_financials(
    ticker: str,
    span: int = 5,
    fiscal_years: list[int] = None,
    session_id: Annotated[str, InjectedToolArg] = "",
) -> dict:
    """
    Pull historical income statement, balance sheet, and cash flow statement for a ticker.

    All values are historical actuals, not projections. Returns a list of annual fiscal periods
    sorted newest-first; each period contains income_statement, balance_sheet, and cash_flow
    sub-objects plus a fiscal_year field. Filter on fiscal_year to access a specific year.

    Args:
        ticker: Stock ticker symbol (e.g. "AAPL").
        span: Number of latest annual fiscal periods (10-K filings) to retrieve. Ignored when
              fiscal_years is provided (span is then computed from the requested years).
        fiscal_years: Explicit list of fiscal years to retrieve (e.g. [2021, 2022]). When given,
                      only those years are returned and the cache is checked by year instead of span.

    Key output fields:
        income_statement.interest_expense       May be None — use falled_back_to_risk_free_rate
                                                in DCF output to detect when cost of debt was
                                                estimated rather than derived.
        income_statement.depreciation_expense   D&A from income statement; may be None due to
                                                XBRL extraction gaps.
        cash_flow.depreciation_amortization     D&A from cash flow statement; may be None. If
                                                None, DCF D&A projection defaults to zero,
                                                understating UFCF and enterprise value.
        cash_flow.cfo                           Operating cash flow. Always compare to net income
                                                to confirm earnings quality.
        cash_flow.fcf                           Computed: CFO minus CapEx. Null if either input
                                                is missing.
        balance_sheet.net_working_capital       Computed: current assets minus current liabilities.
    """
    conn = open_connection(session_id)
    try:
        result, was_cached = FinancialsCache.get_or_fetch(conn, ticker, int(span), fiscal_years, session_id=session_id)
    finally:
        conn.close()
    log_cache_status("get_financials", was_cached, ticker=ticker, span=span, fiscal_years=fiscal_years)
    return {
        "source": "cache" if was_cached else "external",
        "ticker": result.ticker,
        "periods_retrieved": len(result.periods),
        "fiscal_years": [p.fiscal_year for p in result.periods],
    }


@tool
def get_market_data(
    ticker: str,
    include_rfr: bool = True,
    session_id: Annotated[str, InjectedToolArg] = "",
) -> dict:
    """
    Pull current market data (price, beta, shares, market cap) and optional risk-free rate.

    These are trading metrics and WACC inputs — they describe how the stock is priced by the
    market, not how the business operates or competes.

    Args:
        ticker: Stock ticker symbol.
        include_rfr: If True, also fetch the FRED DGS10 10-year Treasury yield as risk-free rate.

    Key output fields:
        current_price        Current stock price. Use for: intrinsic value comparison, per-share
                             context. Not for: measuring operational or business performance.
        market_cap           Total equity market value (price × shares). Use for: WACC equity
                             weight, size context. Not for: evidence of competitive dominance or
                             market share.
        beta                 Historical price covariance with the market index. Use for: CAPM
                             cost of equity. Not for: direct assessment of business or
                             operational risk.
        risk_free_rate       Current 10-year Treasury yield (FRED DGS10). Use for: WACC
                             risk-free component only. Not for: macroeconomic analysis.
        shares_outstanding   Diluted share count. Use for: per-share calculations, dilution
                             tracking. Not for: workforce or operational scale.
    """
    conn = open_connection(session_id)
    try:
        result, was_cached = MarketDataCache.get_or_fetch(conn, ticker, include_rfr, session_id=session_id)
    finally:
        conn.close()
    log_cache_status("get_market_data", was_cached, ticker=ticker, include_rfr=include_rfr)
    return {
        "source": "cache" if was_cached else "external",
        "ticker": ticker,
        "current_price": result.current_price,
        "market_cap": result.market_cap,
        "beta": result.beta,
        "risk_free_rate": result.risk_free_rate,
    }


@tool
def get_sector_data(
    year: int,
    session_id: Annotated[str, InjectedToolArg] = "",
) -> dict:
    """
    Pull sector-level WACC and DCF model parameters for a given year.

    These are model inputs, not sector analysis outputs.

    Key output fields:
        equity_risk_premium    Market-wide excess return assumption. Use for: CAPM / WACC only.
                               Not for: company-specific or sector-specific outlook.
        long_term_growth_rate  GDP-proxy terminal growth assumption (hardcoded at 2.5%). Use
                               for: DCF terminal value only. Not for: company-specific growth
                               forecasts or analyst consensus. This is a model floor, not a
                               prediction.
    """
    conn = open_connection(session_id)
    try:
        result, was_cached = SectorDataCache.get_or_fetch(conn, year, session_id=session_id)
    finally:
        conn.close()
    log_cache_status("get_sector_data", was_cached, year=year)
    return {
        "source": "cache" if was_cached else "external",
        "year": year,
        "equity_risk_premium": result.equity_risk_premium,
        "long_term_growth_rate": result.long_term_growth_rate,
    }


@tool
def scrape_web(
    topic: str,
    max_results: int = 3,
    session_id: Annotated[str, InjectedToolArg] = "",
) -> dict:
    """
    Search the web for recent news, events, or qualitative context on a financial topic.

    The only tool that provides forward-looking, qualitative, or event-specific information.
    No other tool contains recent news, earnings guidance, analyst commentary, product pipeline,
    regulatory developments, or management statements. When the question is forward-looking,
    scrape_web is required — get_market_data and get_sector_data contain no forward-looking
    information and cannot substitute for it.

    Do not use to retrieve numbers already available through financial statement tools.

    Args:
        topic: Description of what to search for (e.g. "Apple Q1 2025 earnings guidance").
        max_results: Number of pages to scrape per search query (default 3).

    Key output fields:
        confidence    Scrape quality score (0–1). Treat results below 0.5 as low confidence —
                      mention the limitation when citing them.
        source_type   Inferred source category. Prefer earnings press releases and SEC filings
                      over generic news when citing financial figures.
    """
    results = search_and_scrape(topic, int(max_results))
    log_cache_status("scrape_web", False, topic=topic)
    return {
        "source": "web",
        "data": [
            {"url": r.url, "title": r.title, "snippet": r.snippet, "confidence": r.confidence}
            for r in results
        ],
    }
