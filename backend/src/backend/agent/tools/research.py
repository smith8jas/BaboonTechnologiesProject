"""Research-phase tools: pull external data (financials, market, sector, web)."""

from datetime import date
from typing import Annotated

from langchain_core.tools import InjectedToolArg, tool

from backend.services import financials as financials_service
from backend.services.scrape import search_and_scrape

from ..cache import find, merge_financials_data, upsert
from .base import log_cache_status


def _fy_str(year) -> str:
    """Normalize a fiscal-year label to the 'FY2023' format stored in research_messages."""
    s = str(year).strip().upper()
    return s if s.startswith("FY") else f"FY{s}"


def _normalize_financials_data(data: dict) -> dict:
    """Guarantee every period has a usable fiscal_year string, even if metadata.fiscal_year_end
    was missing and HistoricalFinancials couldn't derive one."""
    for period in data.get("periods", []):
        if not period.get("fiscal_year"):
            period["fiscal_year"] = _fy_str(period["period_end"][:4])
    return data


@tool
def get_financials(
    ticker: str,
    span: int = 5,
    fiscal_years: list[int] = None,
    research_messages: Annotated[list, InjectedToolArg] = None,
    cycle: Annotated[int, InjectedToolArg] = 0,
) -> dict:
    """
    Pull historical income statement, balance sheet, and cash flow statement for a ticker.

    All values are historical actuals, not projections. Fetches and caches annual fiscal periods
    sorted newest-first; each cached period contains sub-objects for each statement plus a
    fiscal_year field, accessible to calculation tools by fiscal_year.

    Args:
        ticker: Stock ticker symbol (e.g. "AAPL").
        span: Number of latest annual fiscal periods (10-K filings) to retrieve. Ignored when
              fiscal_years is provided (span is then computed from the requested years).
        fiscal_years: Explicit list of fiscal years to retrieve (e.g. [2021, 2022]). When given,
                      only those years are checked for cache coverage instead of span.

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
    t = str(ticker).strip().upper()
    research_messages = research_messages if research_messages is not None else []
    identifier = ("financials", t)
    existing = find(research_messages, identifier)

    if fiscal_years:
        targets = {_fy_str(y) for y in fiscal_years}
        have = {p["fiscal_year"] for p in existing["data"]["periods"]} if existing else set()
        if targets.issubset(have):
            log_cache_status("get_financials", True, ticker=t, span=span, fiscal_years=fiscal_years)
            return {"source": "cache", "data": existing["data"]}
        needed_span = max(int(span), date.today().year - min(int(y) for y in fiscal_years) + 2)
        hf = financials_service.get_cached_financials(t, needed_span)
        new_data = _normalize_financials_data(hf.model_dump(mode="json"))
        entry = upsert(
            research_messages, tool="get_financials", identifier=identifier,
            ticker=t, cycle=cycle, data=new_data, data_source="SEC EDGAR",
            merge=merge_financials_data,
        )
        log_cache_status("get_financials", False, ticker=t, span=span, fiscal_years=fiscal_years)
        return {"source": "external", "data": entry["data"]}

    if existing and len(existing["data"]["periods"]) >= int(span):
        log_cache_status("get_financials", True, ticker=t, span=span)
        return {"source": "cache", "data": existing["data"]}

    hf = financials_service.get_cached_financials(t, int(span))
    new_data = _normalize_financials_data(hf.model_dump(mode="json"))
    entry = upsert(
        research_messages, tool="get_financials", identifier=identifier,
        ticker=t, cycle=cycle, data=new_data, data_source="SEC EDGAR",
        merge=merge_financials_data,
    )
    log_cache_status("get_financials", False, ticker=t, span=span)
    return {"source": "external", "data": entry["data"]}


@tool
def get_market_data(
    ticker: str,
    include_rfr: bool = True,
    research_messages: Annotated[list, InjectedToolArg] = None,
    cycle: Annotated[int, InjectedToolArg] = 0,
) -> dict:
    """
    Pull current market data (price, beta, shares, market cap) and optional risk-free rate.

    These are trading metrics and WACC inputs — they describe how the stock is priced by the
    market, not how the business operates or competes.

    Args:
        ticker: Stock ticker symbol.
        include_rfr: If True, also fetch the FRED DGS10 10-year Treasury yield as risk-free rate.

    Key output fields:
        current_price        Current stock price. Intrinsic value comparison and per-share
                             context; not for operational performance measurement.
        market_cap           Total equity market value (price × shares). WACC equity weight
                             and size context; not a proxy for competitive position.
        beta                 Historical price covariance with the market index. CAPM cost of
                             equity input; not for direct business or operational risk assessment.
        risk_free_rate       Current 10-year Treasury yield (FRED DGS10). WACC risk-free
                             component only; not for macroeconomic analysis.
        shares_outstanding   Diluted share count. Per-share calculations and dilution tracking;
                             not for workforce or operational scale.
    """
    t = str(ticker).strip().upper()
    research_messages = research_messages if research_messages is not None else []
    identifier = ("market_data", t)
    existing = find(research_messages, identifier)

    if existing and (existing["data"].get("risk_free_rate") is not None or not include_rfr):
        log_cache_status("get_market_data", True, ticker=t, include_rfr=include_rfr)
        return {"source": "cache", "data": existing["data"]}

    md = financials_service.get_market_data(t, include_rfr)
    new_data = md.model_dump(mode="json")
    data_source = "Yahoo Finance, FRED (10-Year Treasury)" if include_rfr else "Yahoo Finance"
    entry = upsert(
        research_messages, tool="get_market_data", identifier=identifier,
        ticker=t, cycle=cycle, data=new_data, data_source=data_source,
    )
    log_cache_status("get_market_data", False, ticker=t, include_rfr=include_rfr)
    return {"source": "external", "data": entry["data"]}


@tool
def get_sector_data(
    year: int,
    research_messages: Annotated[list, InjectedToolArg] = None,
    cycle: Annotated[int, InjectedToolArg] = 0,
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
    resolved = int(year or date.today().year)
    research_messages = research_messages if research_messages is not None else []
    identifier = ("sector_data", resolved)
    existing = find(research_messages, identifier)

    if existing:
        log_cache_status("get_sector_data", True, year=resolved)
        return {"source": "cache", "data": existing["data"]}

    sd = financials_service.get_sector_data(resolved)
    new_data = sd.model_dump(mode="json")
    entry = upsert(
        research_messages, tool="get_sector_data", identifier=identifier,
        ticker=None, cycle=cycle, data=new_data, data_source="Damodaran (NYU Stern)",
    )
    log_cache_status("get_sector_data", False, year=resolved)
    return {"source": "external", "data": entry["data"]}


@tool
def scrape_web(
    topic: str,
    max_results: int = 3,
) -> dict:
    """
    Search the web for recent news, events, or qualitative context on a financial topic.

    The only tool that provides forward-looking, qualitative, or event-specific information.
    No other tool contains recent news, earnings guidance, analyst commentary, product pipeline,
    regulatory developments, or management statements.

    Do not use to retrieve numbers already available through financial statement tools.

    Args:
        topic: Description of what to search for (e.g. "Apple Q1 2025 earnings guidance").
        max_results: Number of pages to scrape per search query (default 3).

    Key output fields:
        confidence    Scrape quality score (0–1). Treat results below 0.6 as low confidence —
                      mention the limitation when citing them.
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
