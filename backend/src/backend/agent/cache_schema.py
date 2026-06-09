"""Shared constants for agent tool specs and state-cache structure."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


PHASE_RESEARCH = "research"
PHASE_CALCULATION = "calculation"

CACHE_COMPANIES = "companies"
CACHE_GLOBAL = "global"
CACHE_SEARCHED = "searched"
CACHE_CALCULATED = "calculated"

CACHE_FINANCIALS = "financials"
CACHE_MARKET_DATA = "market_data"
CACHE_SECTOR_DATA_BY_YEAR = "sector_data_by_year"
CACHE_GROWTH = "growth"
CACHE_RATIOS = "ratios"
CACHE_DCF = "dcf"
CACHE_COMPARABLES = "comparables"
CACHE_SCENARIOS = "scenarios"

SUBDOMAIN_INCOME_STATEMENT = "income_statement"
SUBDOMAIN_BALANCE_SHEET = "balance_sheet"
SUBDOMAIN_LIQUIDITY = "liquidity"
SUBDOMAIN_SOLVENCY = "solvency"
SUBDOMAIN_PROFITABILITY = "profitability"
SUBDOMAIN_EFFICIENCY = "efficiency"
SCENARIO_DEFAULT = "default"

DEPENDENCY_FINANCIALS = f"{CACHE_SEARCHED}.{CACHE_FINANCIALS}"
DEPENDENCY_MARKET_DATA = f"{CACHE_SEARCHED}.{CACHE_MARKET_DATA}"
DEPENDENCY_SECTOR_DATA = f"{CACHE_GLOBAL}.{CACHE_SECTOR_DATA_BY_YEAR}"


@dataclass(frozen=True)
class ToolSpec:
    tool: Any
    group: str
    route: str
    capability: str
    phase: str

    @property
    def name(self) -> str:
        return self.tool.name

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "group": self.group,
            "route": self.route,
            "capability": self.capability,
            "phase": self.phase,
        }
