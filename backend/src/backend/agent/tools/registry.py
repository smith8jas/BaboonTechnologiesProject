"""Tool registry: binds every tool to its agent metadata in one place.

Adding a tool:
    1. Implement it in research.py (external data) or calculation.py (derived data).
    2. Append a ToolSpec entry below. Nothing else needs to change — the graph,
       prompts, and streaming labels all read from this registry.
"""

from .base import PHASE_CALCULATION, PHASE_RESEARCH, ToolSpec, apply_tool_spec
from .calculation import (
    get_balance_sheet_growth_rates,
    get_comps_valuation,
    get_efficiency_ratios,
    get_income_statement_growth_rates,
    get_liquidity_ratios,
    get_profitability_ratios,
    get_solvency_ratios,
    run_dcf_valuation,
)
from .research import get_financials, get_market_data, get_sector_data, scrape_web

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
    ToolSpec(
        tool=get_comps_valuation,
        group="comparables",
        route="comparables",
        capability="Run comparable company valuation for a ticker. With peers: computes P/E, EV/EBITDA, EV/Sales, P/S, P/B multiples and returns an implied value band. Without peers: falls back to Damodaran sector median multiples using the company's SIC code.",
        phase=PHASE_CALCULATION,
    ),
]

tools = [apply_tool_spec(spec) for spec in TOOL_SPECS]

TOOLS_BY_NAME = {tool.name: tool for tool in tools}


def serialize_tools():
    """Expose tool metadata to prompts without leaking LangChain internals."""
    serialized = {"research": [], "calculation": []}
    for tool in tools:
        metadata = (getattr(tool, "metadata", None) or {}).get("agent", {})
        phase = metadata.get("phase", "calculation")
        entry = {
            "name": tool.name,
            "description": getattr(tool, "description", "") or "",
            "args": getattr(tool, "args", {}) or {},
            "metadata": metadata,
        }
        serialized.setdefault(phase, []).append(entry)

    return serialized


AVAILABLE_TOOLS = serialize_tools()
