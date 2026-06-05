"""Liquidity and solvency ratio calculations."""

from typing import List, Dict

from backend.processing.schema import HistoricalFinancials
from backend.services.financials import get_financials
import json


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


def dso(
    receivables: List[float],
    revenue: List[float]
) -> List[float | None]:

    return [
        round(r / rev * 365, 2) if rev not in (0, None) and r is not None else None
        for r, rev in zip(receivables, revenue)
    ]


def dio(
    inventory: List[float],
    cogs: List[float]
) -> List[float | None]:

    return [
        round(inv / c * 365, 2) if c not in (0, None) and inv is not None else None
        for inv, c in zip(inventory, cogs)
    ]


def dpo(
    payables: List[float],
    cogs: List[float]
) -> List[float | None]:

    return [
        round(p / c * 365, 2) if c not in (0, None) and p is not None else None
        for p, c in zip(payables, cogs)
    ]


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


def get_efficiency_ratios(financials: HistoricalFinancials) -> Dict[str, Dict[str, float | None]]:
    """Calculate working capital metrics (DSO, DIO, DPO) for historical periods."""

    dates = [f.fiscal_year for f in financials.periods]
    receivables = [f.balance_sheet.accounts_receivable for f in financials.periods]
    inventory = [f.balance_sheet.inventory for f in financials.periods]
    payables = [f.balance_sheet.accounts_payable for f in financials.periods]
    revenue = [f.income_statement.revenue for f in financials.periods]
    cogs = [f.income_statement.cogs for f in financials.periods]

    dso_values = dso(
        receivables,
        revenue
    )

    dio_values = dio(
        inventory,
        cogs
    )

    dpo_values = dpo(
        payables,
        cogs
    )

    return {
        date: {
            "dso": dso_v,
            "dio": dio_v,
            "dpo": dpo_v,
        }
        for date, dso_v, dio_v, dpo_v in zip(
            dates,
            dso_values,
            dio_values,
            dpo_values
        )
    }
