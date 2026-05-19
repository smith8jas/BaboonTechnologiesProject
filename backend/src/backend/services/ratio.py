"""Liquidity and solvency ratio calculations."""

from typing import List


def current_ratio(current_assets: List[float],
                  current_liabilities: List[float]) -> List[float]:
    """
    Current Ratio = Current Assets / Current Liabilities

    Measures short-term liquidity and ability to pay short-term obligations.
    """

    return [
        ca / cl if cl not in (0, None) else 0
        for ca, cl in zip(current_assets, current_liabilities)
    ]


def quick_ratio(current_assets: List[float],
                inventory: List[float],
                current_liabilities: List[float]) -> List[float]:
    """
    Quick Ratio = (Current Assets - Inventory) / Current Liabilities

    Measures immediate liquidity excluding inventory.
    """

    return [
        (ca - inv) / cl if cl not in (0, None) else 0
        for ca, inv, cl in zip(current_assets, inventory, current_liabilities)
    ]


def debt_to_equity(total_liabilities: List[float],
                   total_equity: List[float]) -> List[float]:
    """
    Debt-to-Equity Ratio = Total Liabilities / Total Equity

    Measures leverage and financial risk.
    """

    return [
        tl / te if te not in (0, None) else 0
        for tl, te in zip(total_liabilities, total_equity)
    ]


def interest_coverage(ebit: List[float],
                      interest_expense: List[float]) -> List[float]:
    """
    Interest Coverage Ratio = EBIT / Interest Expense

    Measures ability to cover interest payments using operating profit.
    """

    return [
        e / ie if ie not in (0, None) else 0
        for e, ie in zip(ebit, interest_expense)
    ]