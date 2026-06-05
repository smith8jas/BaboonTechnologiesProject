"""LangChain tools exposed to the agent graph."""

from typing import Dict
from datetime import date

from langchain_core.tools import tool

from backend.processing.schema import DCFOutput, HistoricalFinancials, MarketData, SectorData
from backend.services import dcf_engine, financials, growth, ratio


def agent_tool(
    tool,
    *,
    group: str,
    route: str,
    capability: str,
    requires_financials: bool = False,
):
    metadata = dict(getattr(tool, "metadata", None) or {})
    metadata["agent"] = {
        "group": group,
        "route": route,
        "capability": capability,
        "requires_financials": requires_financials,
    }
    tool.metadata = metadata
    return tool


@tool
def get_financials(ticker: str, span: int = 5) -> HistoricalFinancials:
    """
    Pull, normalize, and validate historical financials for a ticker.

    Args:
        ticker: Stock ticker symbol (e.g. "AAPL").
        span: Number of annual fiscal periods (10-K filings) to retrieve.

    Returns:
        HistoricalFinancials with metadata and per-period statements.
    """
    return financials.get_financials(ticker, span)


@tool
def get_market_data(ticker: str, include_rfr: bool = True) -> MarketData:
    """
    Pull market data (price, beta, shares, market cap) and optional risk-free rate.

    Args:
        ticker: Stock ticker symbol.
        include_rfr: If True, fetch FRED DGS10 risk-free rate.

    Returns:
        MarketData with current market values.
    """
    return financials.get_market_data(ticker, include_rfr)


@tool
def get_sector_data(year) -> SectorData:
    """Pull sector-level financial assumptions for a given year."""
    return financials.get_sector_data(year)


@tool
def get_income_statement_growth_rates(ticker: str, span: int = 5) -> dict:
    """Calculate year-over-year income statement growth rates for a ticker."""
    hf = financials.get_financials(ticker, span)
    return growth.get_income_statement_growth_rates(hf)


@tool
def get_balance_sheet_growth_rates(ticker: str, span: int = 5) -> dict:
    """Calculate year-over-year balance sheet growth rates for a ticker."""
    hf = financials.get_financials(ticker, span)
    return growth.get_balance_sheet_growth_rates(hf)


@tool
def get_liquidity_ratios(
    ticker: str,
    span: int = 5,
) -> Dict[str, Dict[str, float | None]]:
    """Calculate liquidity ratios for a ticker's historical financial periods."""
    hf = financials.get_financials(ticker, span)
    return ratio.get_liquidity_ratios(hf)


@tool
def get_solvency_ratios(
    ticker: str,
    span: int = 5,
) -> Dict[str, Dict[str, float | None]]:
    """Calculate solvency ratios for a ticker's historical financial periods."""
    hf = financials.get_financials(ticker, span)
    return ratio.get_solvency_ratios(hf)


@tool
def get_profitability_ratios(
    ticker: str,
    span: int = 5,
) -> Dict[str, Dict[str, float | None]]:
    """Calculate profitability ratios for a ticker's historical financial periods."""
    hf = financials.get_financials(ticker, span)
    return ratio.get_profitability_ratios(hf)


@tool
def get_efficiency_ratios(
    ticker: str,
    span: int = 5,
) -> Dict[str, Dict[str, float | None]]:
    """Calculate working capital efficiency ratios for a ticker's historical periods."""
    hf = financials.get_financials(ticker, span)
    return ratio.get_efficiency_ratios(hf)


@tool
def run_dcf_valuation(
    ticker: str,
    span: int = 5,
    year: int | None = None,
) -> DCFOutput:
    """Run a full DCF valuation for a public company ticker."""
    year = year or date.today().year
    hf = financials.get_financials(ticker, span)
    md = financials.get_market_data(ticker)
    sd = financials.get_sector_data(year)
    assumptions = dcf_engine.build_assumptions(hf, md, sd)
    valuation_inputs = dcf_engine.build_valuation_inputs(hf, md, sd)
    return dcf_engine.run_dcf(hf, valuation_inputs, assumptions)


financial_tools = [
    agent_tool(
        get_financials,
        group="financial_statement",
        route="financials",
        capability="Pull historical company financial statements by ticker and fiscal-period span.",
    ),
]

market_data_tools = [
    agent_tool(
        get_market_data,
        group="market_data",
        route="market_data",
        capability="Pull current market data such as price, beta, shares, market cap, and optional risk-free rate.",
    ),
]

sector_data_tools = [
    agent_tool(
        get_sector_data,
        group="sector_data",
        route="sector_data",
        capability="Pull sector-level valuation assumptions for a requested year.",
    ),
]

growth_tools = [
    agent_tool(
        get_income_statement_growth_rates,
        group="growth_rate",
        route="growth_rates",
        capability="Calculate year-over-year growth rates for income statement fields.",
        requires_financials=True,
    ),
    agent_tool(
        get_balance_sheet_growth_rates,
        group="growth_rate",
        route="growth_rates",
        capability="Calculate year-over-year growth rates for balance sheet fields.",
        requires_financials=True,
    ),
]

ratio_tools = [
    agent_tool(
        get_liquidity_ratios,
        group="ratio",
        route="ratios",
        capability="Calculate liquidity ratios for historical financial periods.",
        requires_financials=True,
    ),
    agent_tool(
        get_solvency_ratios,
        group="ratio",
        route="ratios",
        capability="Calculate solvency ratios for historical financial periods.",
        requires_financials=True,
    ),
    agent_tool(
        get_profitability_ratios,
        group="ratio",
        route="ratios",
        capability="Calculate profitability ratios for historical financial periods.",
        requires_financials=True,
    ),
    agent_tool(
        get_efficiency_ratios,
        group="ratio",
        route="ratios",
        capability="Calculate working capital efficiency ratios, including DSO, DIO, and DPO, for historical financial periods.",
        requires_financials=True,
    ),
]

dcf_tools = [
    agent_tool(
        run_dcf_valuation,
        group="dcf",
        route="dcf",
        capability="Run a full DCF valuation by ticker using financials, market data, sector assumptions, derived assumptions, and valuation inputs.",
        requires_financials=True,
    ),
]

tools = [
    *financial_tools,
    *market_data_tools,
    *sector_data_tools,
    *growth_tools,
    *ratio_tools,
    *dcf_tools,
]
