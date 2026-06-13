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
    Pull, normalize, and validate historical financials for a ticker.

    Args:
        ticker: Stock ticker symbol (e.g. "AAPL").
        span: Number of latest annual fiscal periods (10-K filings) to retrieve. Ignored when
              fiscal_years is provided (span is then computed from the requested years).
        fiscal_years: Explicit list of fiscal years to retrieve (e.g. [2021, 2022]). When given,
                      only those years are returned and the cache is checked by year instead of span.

    Returns:
        {"source": "cache" | "external", "data": HistoricalFinancials payload}
    """
    conn = open_connection(session_id)
    try:
        result, was_cached = FinancialsCache.get_or_fetch(conn, ticker, int(span), fiscal_years)
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
    Pull market data (price, beta, shares, market cap) and optional risk-free rate.

    Args:
        ticker: Stock ticker symbol.
        include_rfr: If True, fetch FRED DGS10 risk-free rate.

    Returns:
        {"source": "cache" | "external", "data": MarketData payload}
    """
    conn = open_connection(session_id)
    try:
        result, was_cached = MarketDataCache.get_or_fetch(conn, ticker, include_rfr)
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
    """Pull sector-level financial assumptions for a given year."""
    conn = open_connection(session_id)
    try:
        result, was_cached = SectorDataCache.get_or_fetch(conn, year)
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
    Search the web for recent news, events, or public information on a financial topic.
    Use for context not available in financial statements: recent earnings announcements,
    guidance updates, product launches, regulatory events, or analyst commentary.
    Do not use to retrieve numbers already available through financial statement tools.

    Args:
        topic: Description of what to search for (e.g. "Apple Q1 2025 earnings guidance").
        max_results: Number of pages to scrape per search query (default 3).

    Returns:
        {"source": "web", "data": [{"url", "title", "snippet", "confidence"}, ...]}
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
