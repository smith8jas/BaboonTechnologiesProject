from backend.processing.schema import (
    HistoricalFinancials,
    MarketData,
    SectorData,
    Assumptions,
    ValuationInputs
)


def _avg(values: list) -> float | None:
    clean = [v for v in values if v is not None]
    return sum(clean) / len(clean) if clean else None


def build_assumptions(hf: HistoricalFinancials) -> Assumptions: # Can (and should in the near future) accept other classes like 
                                                                # MarketData, SectorData, even SentimentAnalysis!!!
                                                                # This is the heart of the DCF engine!
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


def build_valuation_inputs(hf:HistoricalFinancials, md: MarketData, sd: SectorData) -> ValuationInputs:


    latest_bs = hf.periods[-1].balance_sheet

    interest_expenses = [
        abs(p.income_statement.interest_expense) / p.balance_sheet.long_term_debt
        for p in hf.periods
        if p.income_statement.interest_expense and p.balance_sheet.long_term_debt
    ]
    if not interest_expenses:
        interest_expenses = [
            abs(p.cash_flow.interest_expense) / p.balance_sheet.long_term_debt
            for p in hf.periods
            if p.cash_flow.interest_expense and p.balance_sheet.long_term_debt
        ]

    cost_of_debt = sum(interest_expenses) / len(interest_expenses) if interest_expenses else None

    total_debt = (latest_bs.long_term_debt or 0.0) + (latest_bs.short_term_debt or 0.0)

    # Tax rate — trailing average inline
    tax_rates = [
        p.income_statement.tax_expense / p.income_statement.ebit
        for p in hf.periods
        # if p.income_statement.tax_expense and p.income_statement.ebit     (implement fallback later)
    ]
    tax_rate = sum(tax_rates) / len(tax_rates) if tax_rates else None   # else sd.tax_rates (uncomment once we have 
                                                                        # damodaran tax rates mapped from sic code)

    return ValuationInputs(
        ticker=hf.ticker,
        risk_free_rate=md.risk_free_rate,
        beta=md.beta,
        equity_risk_premium=sd.equity_risk_premium,
        cost_of_debt=cost_of_debt,
        market_cap=md.market_cap,
        shares_outstanding=md.shares_outstanding,
        total_debt=total_debt,
        tax_rate=tax_rate,
        long_term_growth_rate=sd.long_term_growth_rate,
    )
