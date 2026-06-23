"""Calculation-phase tools: derive growth, ratios, DCF, and comps from research_messages.

These tools never perform I/O — they read their dependency from research_messages
(raising CacheMissError if it's not there, never fetching it themselves) and write
their result into calculated_messages unconditionally. Recompute is free, so there's
no staleness check: every call recomputes from whatever financials/market/sector data
is currently known, which only grows as the conversation progresses.

The one exception is get_comps_valuation's Damodaran fallback path, which needs
industry-level sector multiples that have no research tool of their own — it resolves
those itself (read-through-fetch into research_messages) before computing.
"""

from datetime import date
from typing import Annotated, Optional

from langchain_core.tools import InjectedToolArg, tool

from backend.processing.schema import HistoricalFinancials, MarketData, SectorData
from backend.services import comparables as comparables_service
from backend.services import dcf_engine
from backend.services import growth as growth_service
from backend.services import ratio as ratio_service

from ..cache import CacheMissError, find, upsert
from ..cache.schema import (
    SCENARIO_DEFAULT,
    SUBDOMAIN_BALANCE_SHEET,
    SUBDOMAIN_EFFICIENCY,
    SUBDOMAIN_INCOME_STATEMENT,
    SUBDOMAIN_LIQUIDITY,
    SUBDOMAIN_PROFITABILITY,
    SUBDOMAIN_SOLVENCY,
)
from .base import log_cache_status


def _require_financials(research_messages: list, ticker: str, span: int) -> HistoricalFinancials:
    entry = find(research_messages, ("financials", ticker))
    if entry is None or len(entry["data"]["periods"]) < int(span):
        raise CacheMissError(
            f"Financials for {ticker} (span={span}) not in research_messages — "
            "call get_financials before any calculation tool."
        )
    return HistoricalFinancials.model_validate(entry["data"])


@tool
def get_income_statement_growth_rates(
    ticker: str,
    span: int = 5,
    research_messages: Annotated[list, InjectedToolArg] = None,
    calculated_messages: Annotated[list, InjectedToolArg] = None,
    cycle: Annotated[int, InjectedToolArg] = 0,
) -> dict:
    """
    Calculate year-over-year income statement growth rates across the latest span fiscal periods.

    Covers revenue, gross profit, EBIT, and net income. All fields are historical
    percentage changes, not forward projections. Each fiscal_year key holds that single
    period's change versus the immediately preceding period only — never a multi-year
    average or cumulative change. (Contrast with run_dcf_valuation's assumption_revenue_growth,
    which IS a multi-period average — do not conflate the two.)

    Prerequisites: income statement values for ticker across span periods retrieved via
    get_financials(ticker, span).
    """
    t = ticker.strip().upper()
    research_messages = research_messages if research_messages is not None else []
    calculated_messages = calculated_messages if calculated_messages is not None else []

    hf = _require_financials(research_messages, t, span)
    result = growth_service.get_income_statement_growth_rates(hf)
    entry = upsert(
        calculated_messages, tool="get_income_statement_growth_rates",
        identifier=("growth", t, SUBDOMAIN_INCOME_STATEMENT), ticker=t, cycle=cycle, data=result,
        data_source="SEC EDGAR (calculated)",
    )
    log_cache_status("get_income_statement_growth_rates", False, ticker=t, span=span)
    return {"source": "calculated", "data": entry["data"]}


@tool
def get_balance_sheet_growth_rates(
    ticker: str,
    span: int = 5,
    research_messages: Annotated[list, InjectedToolArg] = None,
    calculated_messages: Annotated[list, InjectedToolArg] = None,
    cycle: Annotated[int, InjectedToolArg] = 0,
) -> dict:
    """
    Calculate year-over-year balance sheet growth rates across the latest span fiscal periods.

    Covers total assets, equity, debt, and working capital. All fields are historical
    percentage changes, not forward projections. Each fiscal_year key holds that single
    period's change versus the immediately preceding period only — never a multi-year
    average or cumulative change.

    Prerequisites: balance sheet values for ticker across span periods retrieved via
    get_financials(ticker, span).
    """
    t = ticker.strip().upper()
    research_messages = research_messages if research_messages is not None else []
    calculated_messages = calculated_messages if calculated_messages is not None else []

    hf = _require_financials(research_messages, t, span)
    result = growth_service.get_balance_sheet_growth_rates(hf)
    entry = upsert(
        calculated_messages, tool="get_balance_sheet_growth_rates",
        identifier=("growth", t, SUBDOMAIN_BALANCE_SHEET), ticker=t, cycle=cycle, data=result,
        data_source="SEC EDGAR (calculated)",
    )
    log_cache_status("get_balance_sheet_growth_rates", False, ticker=t, span=span)
    return {"source": "calculated", "data": entry["data"]}


@tool
def get_liquidity_ratios(
    ticker: str,
    span: int = 5,
    research_messages: Annotated[list, InjectedToolArg] = None,
    calculated_messages: Annotated[list, InjectedToolArg] = None,
    cycle: Annotated[int, InjectedToolArg] = 0,
) -> dict:
    """
    Calculate liquidity ratios (current ratio, quick ratio, cash ratio) across the latest
    span fiscal periods.

    Prerequisites: balance sheet values (current assets, current liabilities, cash) for ticker
    across span periods retrieved via get_financials(ticker, span).
    """
    t = ticker.strip().upper()
    research_messages = research_messages if research_messages is not None else []
    calculated_messages = calculated_messages if calculated_messages is not None else []

    hf = _require_financials(research_messages, t, span)
    result = ratio_service.get_liquidity_ratios(hf)
    entry = upsert(
        calculated_messages, tool="get_liquidity_ratios",
        identifier=("ratios", t, SUBDOMAIN_LIQUIDITY), ticker=t, cycle=cycle, data=result,
        data_source="SEC EDGAR (calculated)",
    )
    log_cache_status("get_liquidity_ratios", False, ticker=t, span=span)
    return {"source": "calculated", "data": entry["data"]}


@tool
def get_solvency_ratios(
    ticker: str,
    span: int = 5,
    research_messages: Annotated[list, InjectedToolArg] = None,
    calculated_messages: Annotated[list, InjectedToolArg] = None,
    cycle: Annotated[int, InjectedToolArg] = 0,
) -> dict:
    """
    Calculate solvency ratios (debt-to-equity, debt-to-assets, interest coverage) across the
    latest span fiscal periods.

    Prerequisites: income statement (EBIT, interest expense) and balance sheet (total debt,
    total assets, equity) values for ticker across span periods retrieved via
    get_financials(ticker, span).
    """
    t = ticker.strip().upper()
    research_messages = research_messages if research_messages is not None else []
    calculated_messages = calculated_messages if calculated_messages is not None else []

    hf = _require_financials(research_messages, t, span)
    result = ratio_service.get_solvency_ratios(hf)
    entry = upsert(
        calculated_messages, tool="get_solvency_ratios",
        identifier=("ratios", t, SUBDOMAIN_SOLVENCY), ticker=t, cycle=cycle, data=result,
        data_source="SEC EDGAR (calculated)",
    )
    log_cache_status("get_solvency_ratios", False, ticker=t, span=span)
    return {"source": "calculated", "data": entry["data"]}


@tool
def get_profitability_ratios(
    ticker: str,
    span: int = 5,
    research_messages: Annotated[list, InjectedToolArg] = None,
    calculated_messages: Annotated[list, InjectedToolArg] = None,
    cycle: Annotated[int, InjectedToolArg] = 0,
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
    t = ticker.strip().upper()
    research_messages = research_messages if research_messages is not None else []
    calculated_messages = calculated_messages if calculated_messages is not None else []

    hf = _require_financials(research_messages, t, span)
    result = ratio_service.get_profitability_ratios(hf)
    entry = upsert(
        calculated_messages, tool="get_profitability_ratios",
        identifier=("ratios", t, SUBDOMAIN_PROFITABILITY), ticker=t, cycle=cycle, data=result,
        data_source="SEC EDGAR (calculated)",
    )
    log_cache_status("get_profitability_ratios", False, ticker=t, span=span)
    return {"source": "calculated", "data": entry["data"]}


@tool
def get_efficiency_ratios(
    ticker: str,
    span: int = 5,
    research_messages: Annotated[list, InjectedToolArg] = None,
    calculated_messages: Annotated[list, InjectedToolArg] = None,
    cycle: Annotated[int, InjectedToolArg] = 0,
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
    t = ticker.strip().upper()
    research_messages = research_messages if research_messages is not None else []
    calculated_messages = calculated_messages if calculated_messages is not None else []

    hf = _require_financials(research_messages, t, span)
    result = ratio_service.get_efficiency_ratios(hf)
    entry = upsert(
        calculated_messages, tool="get_efficiency_ratios",
        identifier=("ratios", t, SUBDOMAIN_EFFICIENCY), ticker=t, cycle=cycle, data=result,
        data_source="SEC EDGAR (calculated)",
    )
    log_cache_status("get_efficiency_ratios", False, ticker=t, span=span)
    return {"source": "calculated", "data": entry["data"]}


@tool
def run_dcf_valuation(
    ticker: str,
    span: int = 5,
    year: int = 0,
    research_messages: Annotated[list, InjectedToolArg] = None,
    calculated_messages: Annotated[list, InjectedToolArg] = None,
    cycle: Annotated[int, InjectedToolArg] = 0,
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
        assumption_revenue_growth      The single flat growth rate applied to every projected
                                       year. It is the AVERAGE of the year-over-year revenue
                                       growth rates across assumption_span_years of historical
                                       periods (e.g. 4 YoY deltas averaged if span=5) — not the
                                       most recent single fiscal year's growth. Never describe
                                       it as "last year's growth" or conflate it with the most
                                       recent entry from get_income_statement_growth_rates;
                                       those are a different, single-period number.
        assumption_ebit_margin,
        assumption_da_over_revenue,
        assumption_capex_over_revenue,
        assumption_nwc_over_revenue     Same convention: each is a flat historical average over
                                       assumption_span_years periods, held constant across every
                                       projected year. Not a trend, not a single-period actual.
        assumption_span_years          Number of historical fiscal periods averaged into the
                                       five assumption_* fields above.
    """
    t = ticker.strip().upper()
    year = int(year or date.today().year)
    research_messages = research_messages if research_messages is not None else []
    calculated_messages = calculated_messages if calculated_messages is not None else []

    fin_entry = find(research_messages, ("financials", t))
    mkt_entry = find(research_messages, ("market_data", t))
    sector_entry = find(research_messages, ("sector_data", year))
    if fin_entry is None or len(fin_entry["data"]["periods"]) < int(span) or mkt_entry is None or sector_entry is None:
        raise CacheMissError(
            f"DCF for {t} requires financials(span={span}), market_data, and sector_data({year}) "
            "in research_messages — call get_financials, get_market_data, and get_sector_data first."
        )

    hf = HistoricalFinancials.model_validate(fin_entry["data"])
    md = MarketData.model_validate(mkt_entry["data"])
    sd = SectorData.model_validate(sector_entry["data"])

    assumptions = dcf_engine.build_assumptions(hf, md, sd)
    valuation_inputs = dcf_engine.build_valuation_inputs(hf, md, sd, assumptions)
    result = dcf_engine.run_dcf(hf, valuation_inputs, assumptions)

    entry = upsert(
        calculated_messages, tool="run_dcf_valuation",
        identifier=("dcf", t, SCENARIO_DEFAULT), ticker=t, cycle=cycle,
        data=result.model_dump(mode="json"),
        data_source="SEC EDGAR, Yahoo Finance, FRED, Damodaran (NYU Stern) — DCF model output",
    )
    log_cache_status("run_dcf_valuation", False, ticker=t, span=span, year=year)
    return {"source": "calculated", "data": entry["data"]}


@tool
def get_comps_valuation(
    ticker: str,
    peers: Optional[list[str]] = None,
    research_messages: Annotated[list, InjectedToolArg] = None,
    calculated_messages: Annotated[list, InjectedToolArg] = None,
    cycle: Annotated[int, InjectedToolArg] = 0,
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
    t = ticker.strip().upper()
    research_messages = research_messages if research_messages is not None else []
    calculated_messages = calculated_messages if calculated_messages is not None else []

    target_fin_entry = find(research_messages, ("financials", t))
    target_mkt_entry = find(research_messages, ("market_data", t))
    if target_fin_entry is None or target_mkt_entry is None:
        raise CacheMissError(
            f"Comparables for {t} require financials and market data in research_messages — "
            "call get_financials and get_market_data first."
        )
    target_fin = HistoricalFinancials.model_validate(target_fin_entry["data"])
    target_mkt = MarketData.model_validate(target_mkt_entry["data"])

    if peers:
        peer_key = ",".join(sorted(p.strip().upper() for p in peers))
        resolved: list[tuple[str, HistoricalFinancials, MarketData]] = []
        dropped: list[dict] = []
        for p in peers:
            pt = p.strip().upper()
            fin_e = find(research_messages, ("financials", pt))
            mkt_e = find(research_messages, ("market_data", pt))
            if fin_e is None or mkt_e is None:
                dropped.append({"ticker": pt, "reason": "financials/market data not cached for this peer"})
                continue
            resolved.append((pt, HistoricalFinancials.model_validate(fin_e["data"]), MarketData.model_validate(mkt_e["data"])))

        result = comparables_service.peer_comps(target_fin, target_mkt, resolved, dropped)
        identifier = ("comparables", t, "peer", peer_key)
        comps_source = "SEC EDGAR, Yahoo Finance (peer comparables)"
    else:
        industry, notes = comparables_service.resolve_damodaran_industry(target_fin)
        if industry is None:
            log_cache_status("get_comps_valuation", False, ticker=t)
            return {"source": "calculated", "data": {"error": "Damodaran industry unresolved", "notes": notes}}

        dam_entry = find(research_messages, ("damodaran_sector", industry))
        if dam_entry is None:
            from backend.adapters.damodaran import fetch_ev_sales, fetch_price_sales, fetch_trailing_pe
            sector_multiples = {
                "ev_sales": fetch_ev_sales(industry),
                "price_sales": fetch_price_sales(industry),
                "trailing_pe": fetch_trailing_pe(industry),
            }
            dam_entry = upsert(
                research_messages, tool="get_comps_valuation",
                identifier=("damodaran_sector", industry), ticker=None, cycle=cycle, data=sector_multiples,
                data_source="Damodaran (NYU Stern)",
            )

        result = comparables_service.damodaran_fallback(target_fin, target_mkt, industry, notes, dam_entry["data"])
        identifier = ("comparables", t, "damodaran", None)
        comps_source = "SEC EDGAR, Yahoo Finance, Damodaran (NYU Stern) — sector multiples fallback"

    entry = upsert(
        calculated_messages, tool="get_comps_valuation", identifier=identifier, ticker=t, cycle=cycle,
        data=result, data_source=comps_source,
    )
    log_cache_status("get_comps_valuation", False, ticker=t)
    return {"source": "calculated", "data": entry["data"]}
