from backend.processing.schema import (
    HistoricalFinancials,
    Assumptions,
)


def _avg(values: list) -> float | None:
    clean = [v for v in values if v is not None]
    return sum(clean) / len(clean) if clean else None


def build_assumptions(hf: HistoricalFinancials) -> Assumptions:
    periods = hf.periods
    rev = [p.income_statement.revenue for p in periods]

    revenue_growth = _avg([
        (rev[i] - rev[i-1]) / abs(rev[i-1])
        for i in range(1, len(rev))
        if rev[i] is not None and rev[i-1]
    ])

    ebit_margin = _avg([
        p.income_statement.ebit / p.income_statement.revenue
        for p in periods
        if p.income_statement.ebit and p.income_statement.revenue
    ])

    tax_rate = _avg([
        p.income_statement.tax_expense / p.income_statement.ebit
        for p in periods
        if p.income_statement.tax_expense and p.income_statement.ebit
    ])

    da_pct = _avg([
        p.cash_flow.depreciation_amortization / p.income_statement.revenue
        for p in periods
        if p.cash_flow.depreciation_amortization and p.income_statement.revenue
    ])

    capex_pct = _avg([
        p.cash_flow.capex / p.income_statement.revenue
        for p in periods
        if p.cash_flow.capex and p.income_statement.revenue
    ])

    nwc_pct = _avg([
        p.balance_sheet.net_working_capital / p.income_statement.revenue
        for p in periods
        if p.balance_sheet.net_working_capital is not None and p.income_statement.revenue
    ])

    derived = {
        "revenue_growth":                               revenue_growth or 0.0,
        "ebit_margin":                                  ebit_margin    or 0.0,
        "tax_rate":                                     min(max(tax_rate or 0.21, 0.0), 0.6),
        "depreciation_and_amortization_over_revenue":   da_pct or 0.0,
        "capex_over_revenue":                           capex_pct      or 0.0,
        "nwc_over_revenue":                             nwc_pct        or 0.0,
    }
    return Assumptions(**derived)