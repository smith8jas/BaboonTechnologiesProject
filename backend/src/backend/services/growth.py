"""Growth rate calculations."""

from langchain_core.tools import tool

from backend.processing.schema import HistoricalFinancials
from backend.services.financials import get_financials
from backend.services.tool_metadata import agent_tool
import json


def main():
    hf = get_financials("NVDA", 8)
    print(json.dumps(get_income_statement_growth_rates(hf), indent=2))
    print(json.dumps(get_balance_sheet_growth_rates(hf), indent=2))


def _growth(prev: float | None, curr: float | None) -> float | None:
    if prev and curr and prev != 0:
        return round((curr - prev) / abs(prev), 4)
    return None


@tool
def get_income_statement_growth_rates(hf: HistoricalFinancials) -> dict:
    """Calculate year-over-year growth rates for income statement fields."""
    result = {}
    periods = hf.periods
    for i, p in enumerate(periods):
        if i == 0:
            result[p.fiscal_year] = {k: None for k in p.income_statement.model_dump()}
            continue
        prev = periods[i - 1].income_statement.model_dump()
        curr = p.income_statement.model_dump()
        result[p.fiscal_year] = {
            k: _growth(prev[k], curr[k]) for k in curr
        }
    return result


@tool
def get_balance_sheet_growth_rates(hf: HistoricalFinancials) -> dict:
    """Calculate year-over-year growth rates for balance sheet fields."""
    result = {}
    periods = hf.periods
    for i, p in enumerate(periods):
        if i == 0:
            result[p.fiscal_year] = {k: None for k in p.balance_sheet.model_dump()}
            continue
        prev = periods[i - 1].balance_sheet.model_dump()
        curr = p.balance_sheet.model_dump()
        result[p.fiscal_year] = {
            k: _growth(prev[k], curr[k]) for k in curr
        }
    return result


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


if __name__ == "__main__":
    main()
