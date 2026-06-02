"""Liquidity and solvency ratio calculations."""

from typing import List, Dict

from langchain_core.tools import tool

from backend.processing.schema import HistoricalFinancials
from backend.services.financials import get_financials
from backend.services.tool_metadata import agent_tool
import json


def main():
    hf = get_financials("TSLA", 5)
    print(hf.model_dump_json(indent=2))
    print("=======================")
    solvency_ratios = get_solvency_ratios(hf)
    print(json.dumps(solvency_ratios, indent=2))
    print("=======================")
    liquidity_ratios = get_liquidity_ratios(hf)
    print(json.dumps(liquidity_ratios, indent=2))
    print("=======================")
    profitability_ratios = get_profitability_ratios(hf)
    print(json.dumps(profitability_ratios, indent=2))


def current_ratio(
    current_assets: List[float],
    current_liabilities: List[float]
) -> List[float | None]:

    return [
        round(ca / cl, 2) if cl not in (0, None) else None
        for ca, cl in zip(current_assets, current_liabilities)
    ]


def quick_ratio(
    current_assets: List[float],
    inventory: List[float],
    current_liabilities: List[float]
) -> List[float | None]:

    return [
        round((ca - inv) / cl, 2) if cl not in (0, None) else None
        for ca, inv, cl in zip(
            current_assets,
            inventory,
            current_liabilities
        )
    ]


def cash_ratio(
    cash: List[float],
    current_liabilities: List[float]
) -> List[float | None]:

    return [
        round(c / cl, 2) if cl not in (0, None) else None
        for c, cl in zip(cash, current_liabilities)
    ]


def debt_to_equity(
    total_liabilities: List[float],
    total_equity: List[float]
) -> List[float | None]:

    return [
        round(tl / te, 2) if te not in (0, None) else None
        for tl, te in zip(total_liabilities, total_equity)
    ]


def debt_to_assets(
    total_liabilities: List[float],
    total_assets: List[float]
) -> List[float | None]:

    return [
        round(tl / ta, 2) if ta not in (0, None) else None
        for tl, ta in zip(total_liabilities, total_assets)
    ]


def interest_coverage(
    ebit: List[float],
    interest_expense: List[float]
) -> List[float | None]:

    return [
        round(e / ie, 2) if ie not in (0, None) else None
        for e, ie in zip(ebit, interest_expense)
    ]


def gross_profit_margin(
    gross_profit: List[float],
    revenue: List[float]
) -> List[float | None]:

    return [
        round(g / r, 2) if r not in (0, None) else None
        for g, r in zip(gross_profit, revenue)
    ]


def ebit_margin(
    ebit: List[float],
    revenue: List[float]
) -> List[float | None]:

    return [
        round(e / r, 2) if r not in (0, None) else None
        for e, r in zip(ebit, revenue)
    ]


def net_margin(
    net_income: List[float],
    revenue: List[float]
) -> List[float | None]:

    return [
        round(ni / r, 2) if r not in (0, None) else None
        for ni, r in zip(net_income, revenue)
    ]


@tool
def get_liquidity_ratios(financials: HistoricalFinancials) -> Dict[str, Dict[str, float | None]]:
    """Calculate liquidity ratios for historical financial periods."""

    dates = [f.fiscal_year for f in financials.periods]
    current_assets = [f.balance_sheet.total_current_assets for f in financials.periods]
    current_liabilities = [f.balance_sheet.total_current_liabilities for f in financials.periods]
    inventory = [f.balance_sheet.inventory for f in financials.periods]
    cash = [f.balance_sheet.cash for f in financials.periods]

    current_ratios = current_ratio(
        current_assets,
        current_liabilities
    )

    quick_ratios = quick_ratio(
        current_assets,
        inventory,
        current_liabilities
    )

    cash_ratios = cash_ratio(
        cash,
        current_liabilities
    )

    return {
        date: {
            "current_ratio": cr,
            "quick_ratio": qr,
            "cash_ratio": car,
        }
        for date, cr, qr, car in zip(
            dates,
            current_ratios,
            quick_ratios,
            cash_ratios
        )
    }


@tool
def get_solvency_ratios(financials: HistoricalFinancials) -> Dict[str, Dict[str, float | None]]:
    """Calculate solvency ratios for historical financial periods."""

    dates = [f.fiscal_year for f in financials.periods]

    total_liabilities = [f.balance_sheet.total_liabilities for f in financials.periods]
    total_equity = [f.balance_sheet.total_equity for f in financials.periods]
    total_assets = [f.balance_sheet.total_assets for f in financials.periods]
    ebit = [f.income_statement.ebit for f in financials.periods]
    interest_expense = [f.income_statement.interest_expense for f in financials.periods]

    debt_equity_ratios = debt_to_equity(
        total_liabilities,
        total_equity
    )

    debt_assets_ratios = debt_to_assets(
        total_liabilities,
        total_assets
    )

    interest_coverages = interest_coverage(
        ebit,
        interest_expense
    )

    return {
        date: {
            "debt_to_equity": de,
            "debt_to_assets": da,
            "interest_coverage": ic,
        }
        for date, de, da, ic in zip(
            dates,
            debt_equity_ratios,
            debt_assets_ratios,
            interest_coverages
        )
    }


@tool
def get_profitability_ratios(financials: HistoricalFinancials) -> Dict[str, Dict[str, float | None]]:
    """Calculate profitability ratios for historical financial periods."""

    dates = [f.fiscal_year for f in financials.periods]

    revenue = [f.income_statement.revenue for f in financials.periods]
    gross_profit = [f.income_statement.gross_profit for f in financials.periods]
    ebit = [f.income_statement.ebit for f in financials.periods]
    net_income = [f.income_statement.net_income for f in financials.periods]

    gross_profit_margins = gross_profit_margin(
        gross_profit,
        revenue
    )

    ebit_margins = ebit_margin(
        ebit,
        revenue
    )

    net_margins = net_margin(
        net_income,
        revenue
    )

    return {
        date: {
            "gross_profit_margin": gpm,
            "ebit_margin": em,
            "net_profit_margin": npm,
        }
        for date, gpm, em, npm in zip(
            dates,
            gross_profit_margins,
            ebit_margins,
            net_margins
        )
    }


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
]


if __name__ == "__main__":
    main()
