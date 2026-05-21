"""Liquidity and solvency ratio calculations."""

from typing import List, Dict


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


def get_liquidity_ratios(fin) -> Dict[str, Dict[str, float | None]]:

    dates = fin["dates"]

    current_assets = fin["current_assets"]
    current_liabilities = fin["current_liabilities"]
    inventory = fin["inventory"]
    cash = fin["cash"]

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


def get_solvency_ratios(fin) -> Dict[str, Dict[str, float | None]]:

    dates = fin["dates"]

    total_liabilities = fin["total_liabilities"]
    total_equity = fin["total_equity"]
    total_assets = fin["total_assets"]
    ebit = fin["ebit"]
    interest_expense = fin["interest_expense"]

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


