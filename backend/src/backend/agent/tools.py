"""LangChain tools exposed to the agent graph."""

import logging
from typing import Annotated, Dict
from datetime import date

from langchain_core.tools import InjectedToolArg, tool

from backend.processing.schema import DCFOutput, HistoricalFinancials, MarketData, SectorData
from backend.services.scrape import search_and_scrape
from .cache import (
    get_or_calculate_dcf,
    get_or_calculate_growth,
    get_or_calculate_ratios,
    get_or_fetch_financials,
    get_or_fetch_market_data,
    get_or_fetch_sector_data,
    empty_data_cache,
)
from .cache_schema import (
    PHASE_CALCULATION,
    PHASE_RESEARCH,
    SUBDOMAIN_BALANCE_SHEET,
    SUBDOMAIN_EFFICIENCY,
    SUBDOMAIN_INCOME_STATEMENT,
    SUBDOMAIN_LIQUIDITY,
    SUBDOMAIN_PROFITABILITY,
    SUBDOMAIN_SOLVENCY,
    ToolSpec,
)

logger = logging.getLogger(__name__)


def _tool_cache(data_cache: dict | None) -> dict:
    return data_cache if data_cache is not None else empty_data_cache()


def apply_tool_spec(spec: ToolSpec):
    metadata = dict(getattr(spec.tool, "metadata", None) or {})
    metadata["agent"] = spec.metadata
    spec.tool.metadata = metadata
    return spec.tool


def _log_cache_status(tool_name: str, was_cached: bool, **kwargs) -> None:
    details = ", ".join(f"{key}={value}" for key, value in kwargs.items() if value is not None)
    source = "cache" if was_cached else "external"
    logger.info("%s: data from %s%s", tool_name, source, f" ({details})" if details else "")


@tool
def get_financials(
    ticker: str,
    span: int = 5,
    fiscal_years: list[int] | None = None,
    data_cache: Annotated[dict, InjectedToolArg] = None,
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
    result, was_cached = get_or_fetch_financials(
        _tool_cache(data_cache), ticker, int(span), fiscal_years
    )
    _log_cache_status("get_financials", was_cached, ticker=ticker, span=span, fiscal_years=fiscal_years)
    return {"source": "cache" if was_cached else "external", "data": result.model_dump(mode="json")}


@tool
def get_market_data(
    ticker: str,
    include_rfr: bool = True,
    data_cache: Annotated[dict, InjectedToolArg] = None,
) -> dict:
    """
    Pull market data (price, beta, shares, market cap) and optional risk-free rate.

    Args:
        ticker: Stock ticker symbol.
        include_rfr: If True, fetch FRED DGS10 risk-free rate.

    Returns:
        {"source": "cache" | "external", "data": MarketData payload}
    """
    result, was_cached = get_or_fetch_market_data(_tool_cache(data_cache), ticker, include_rfr)
    _log_cache_status("get_market_data", was_cached, ticker=ticker, include_rfr=include_rfr)
    return {"source": "cache" if was_cached else "external", "data": result.model_dump(mode="json")}


@tool
def get_sector_data(
    year,
    data_cache: Annotated[dict, InjectedToolArg] = None,
) -> dict:
    """Pull sector-level financial assumptions for a given year."""
    result, was_cached = get_or_fetch_sector_data(_tool_cache(data_cache), year)
    _log_cache_status("get_sector_data", was_cached, year=year)
    return {"source": "cache" if was_cached else "external", "data": result.model_dump(mode="json")}


@tool
def get_income_statement_growth_rates(
    ticker: str,
    span: int = 5,
    data_cache: Annotated[dict, InjectedToolArg] = None,
) -> dict:
    """Calculate year-over-year income statement growth rates across the latest span fiscal periods."""
    result, was_cached = get_or_calculate_growth(
        _tool_cache(data_cache),
        ticker,
        int(span),
        SUBDOMAIN_INCOME_STATEMENT,
    )
    _log_cache_status("get_income_statement_growth_rates", was_cached, ticker=ticker, span=span)
    return {"source": "cache" if was_cached else "external", "data": result}


@tool
def get_balance_sheet_growth_rates(
    ticker: str,
    span: int = 5,
    data_cache: Annotated[dict, InjectedToolArg] = None,
) -> dict:
    """Calculate year-over-year balance sheet growth rates across the latest span fiscal periods."""
    result, was_cached = get_or_calculate_growth(
        _tool_cache(data_cache),
        ticker,
        int(span),
        SUBDOMAIN_BALANCE_SHEET,
    )
    _log_cache_status("get_balance_sheet_growth_rates", was_cached, ticker=ticker, span=span)
    return {"source": "cache" if was_cached else "external", "data": result}


@tool
def get_liquidity_ratios(
    ticker: str,
    span: int = 5,
    data_cache: Annotated[dict, InjectedToolArg] = None,
) -> dict:
    """Calculate liquidity ratios across the latest span fiscal periods."""
    result, was_cached = get_or_calculate_ratios(
        _tool_cache(data_cache),
        ticker,
        int(span),
        SUBDOMAIN_LIQUIDITY,
    )
    _log_cache_status("get_liquidity_ratios", was_cached, ticker=ticker, span=span)
    return {"source": "cache" if was_cached else "external", "data": result}


@tool
def get_solvency_ratios(
    ticker: str,
    span: int = 5,
    data_cache: Annotated[dict, InjectedToolArg] = None,
) -> dict:
    """Calculate solvency ratios across the latest span fiscal periods."""
    result, was_cached = get_or_calculate_ratios(
        _tool_cache(data_cache),
        ticker,
        int(span),
        SUBDOMAIN_SOLVENCY,
    )
    _log_cache_status("get_solvency_ratios", was_cached, ticker=ticker, span=span)
    return {"source": "cache" if was_cached else "external", "data": result}


@tool
def get_profitability_ratios(
    ticker: str,
    span: int = 5,
    data_cache: Annotated[dict, InjectedToolArg] = None,
) -> dict:
    """Calculate profitability ratios across the latest span fiscal periods."""
    result, was_cached = get_or_calculate_ratios(
        _tool_cache(data_cache),
        ticker,
        int(span),
        SUBDOMAIN_PROFITABILITY,
    )
    _log_cache_status("get_profitability_ratios", was_cached, ticker=ticker, span=span)
    return {"source": "cache" if was_cached else "external", "data": result}


@tool
def get_efficiency_ratios(
    ticker: str,
    span: int = 5,
    data_cache: Annotated[dict, InjectedToolArg] = None,
) -> dict:
    """Calculate working capital efficiency ratios across the latest span fiscal periods."""
    result, was_cached = get_or_calculate_ratios(
        _tool_cache(data_cache),
        ticker,
        int(span),
        SUBDOMAIN_EFFICIENCY,
    )
    _log_cache_status("get_efficiency_ratios", was_cached, ticker=ticker, span=span)
    return {"source": "cache" if was_cached else "external", "data": result}


@tool
def scrape_web(
    topic: str,
    max_results: int = 3,
    data_cache: Annotated[dict, InjectedToolArg] = None,
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
    _log_cache_status("scrape_web", False, topic=topic)
    return {
        "source": "web",
        "data": [
            {"url": r.url, "title": r.title, "snippet": r.snippet, "confidence": r.confidence}
            for r in results
        ],
    }


@tool
def run_dcf_valuation(
    ticker: str,
    span: int = 5,
    year: int | None = None,
    data_cache: Annotated[dict, InjectedToolArg] = None,
) -> dict:
    """Run a full DCF valuation for a public company ticker."""
    year = year or date.today().year
    result, was_cached = get_or_calculate_dcf(_tool_cache(data_cache), ticker, int(span), int(year))
    _log_cache_status("run_dcf_valuation", was_cached, ticker=ticker, span=span, year=year)
    return {
        "source": "cache" if was_cached else "external",
        "data": DCFOutput.model_validate(result).model_dump(mode="json"),
    }


TOOL_SPECS = [
    ToolSpec(
        tool=get_financials,
        group="financial_statement",
        route="financials",
        capability="Pull historical company financial statements by ticker for the latest fiscal-period span.",
        phase=PHASE_RESEARCH,
    ),
    ToolSpec(
        tool=get_market_data,
        group="market_data",
        route="market_data",
        capability="Pull current market data such as price, beta, shares, market cap, and optional risk-free rate.",
        phase=PHASE_RESEARCH,
    ),
    ToolSpec(
        tool=get_sector_data,
        group="sector_data",
        route="sector_data",
        capability="Pull sector-level valuation assumptions for a requested year.",
        phase=PHASE_RESEARCH,
    ),
    ToolSpec(
        tool=get_income_statement_growth_rates,
        group="growth_rate",
        route="growth_rates",
        capability="Calculate year-over-year growth rates for income statement fields over the latest fiscal-period span.",
        phase=PHASE_CALCULATION,
    ),
    ToolSpec(
        tool=get_balance_sheet_growth_rates,
        group="growth_rate",
        route="growth_rates",
        capability="Calculate year-over-year growth rates for balance sheet fields over the latest fiscal-period span.",
        phase=PHASE_CALCULATION,
    ),
    ToolSpec(
        tool=get_liquidity_ratios,
        group="ratio",
        route="ratios",
        capability="Calculate liquidity ratios over the latest fiscal-period span.",
        phase=PHASE_CALCULATION,
    ),
    ToolSpec(
        tool=get_solvency_ratios,
        group="ratio",
        route="ratios",
        capability="Calculate solvency ratios over the latest fiscal-period span.",
        phase=PHASE_CALCULATION,
    ),
    ToolSpec(
        tool=get_profitability_ratios,
        group="ratio",
        route="ratios",
        capability="Calculate profitability ratios over the latest fiscal-period span.",
        phase=PHASE_CALCULATION,
    ),
    ToolSpec(
        tool=get_efficiency_ratios,
        group="ratio",
        route="ratios",
        capability="Calculate working capital efficiency ratios, including DSO, DIO, and DPO, over the latest fiscal-period span.",
        phase=PHASE_CALCULATION,
    ),
    ToolSpec(
        tool=run_dcf_valuation,
        group="dcf",
        route="dcf",
        capability="Run a full DCF valuation by ticker; this composite tool already gets or reuses financials, market data, sector data, derived assumptions, and valuation inputs.",
        phase=PHASE_CALCULATION,
    ),
    ToolSpec(
        tool=scrape_web,
        group="web_scrape",
        route="scrape",
        capability="Search the web and scrape recent news, events, or qualitative context on a financial topic. Use for information not available in structured financial statements.",
        phase=PHASE_RESEARCH,
    ),
]

tools = [apply_tool_spec(spec) for spec in TOOL_SPECS]
