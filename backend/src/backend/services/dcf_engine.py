"""DCF projection and valuation calculations.

Assumptions are produced by the forecast engine (services.forecast) — flatten
a ForecastAssumptions artifact via to_assumptions() and pass it (plus the
artifact itself as `forecast=`) into run_dcf.
"""

from backend.processing.schema import (
    HistoricalFinancials,
    MarketData,
    SectorData,
    Assumptions,
    ForecastAssumptions,
    ValuationInputs,
    DCFOutput
)

# When a forecast artifact supplies terminal growth, keep g at least this far
# below WACC so the Gordon Growth terminal value stays finite and positive.
TERMINAL_WACC_BUFFER = 0.005

_FORECAST_DRIVERS = (
    "revenue_growth", "ebit_margin", "tax_rate", "da_over_revenue",
    "capex_over_revenue", "nwc_over_revenue", "terminal_growth",
)


def build_valuation_inputs(hf: HistoricalFinancials, md: MarketData, sd: SectorData, a: Assumptions) -> ValuationInputs:
    """Combine company, market, and sector data into WACC and equity bridge inputs."""
    latest_bs = hf.periods[-1].balance_sheet
    total_debt = (latest_bs.long_term_debt or 0.0) + (latest_bs.short_term_debt or 0.0)
    total_cash = (latest_bs.cash)

    falled_back_to_risk_free_rate = False

    if total_debt == 0:
        # Debt weight in WACC is zero — cost_of_debt is irrelevant
        cost_of_debt = 0.0
    else:
        # Level 1: IS interest_expense / long_term_debt
        rates = [
            abs(p.income_statement.interest_expense) / (p.balance_sheet.short_term_debt + p.balance_sheet.long_term_debt)
            for p in hf.periods
            if p.income_statement.interest_expense and p.balance_sheet.long_term_debt and p.balance_sheet.short_term_debt
        ]
        # Level 2: CFS interest_expense / long_term_debt
        if not rates:
            rates = [
                abs(p.cash_flow.interest_expense) / p.balance_sheet.long_term_debt
                for p in hf.periods
                if p.cash_flow.interest_expense and p.balance_sheet.long_term_debt
            ]
        # Level 3: back-calculate from EBIT - (net_income + tax_expense)
        if not rates:
            rates = [
                (p.income_statement.ebit - p.income_statement.net_income - p.income_statement.tax_expense)
                / p.balance_sheet.long_term_debt
                for p in hf.periods
                if all(x is not None for x in [
                    p.income_statement.ebit,
                    p.income_statement.net_income,
                    p.income_statement.tax_expense,
                ]) and p.balance_sheet.long_term_debt
            ]
            rates = [r for r in rates if r > 0]
        # Level 4: risk-free rate + 150bps floor
        if rates:
            cost_of_debt = sum(rates) / len(rates)
        else:
            cost_of_debt = md.risk_free_rate + 0.015
            falled_back_to_risk_free_rate = True

    return ValuationInputs(
        ticker=hf.ticker,
        risk_free_rate=md.risk_free_rate,
        beta=md.beta,
        equity_risk_premium=sd.equity_risk_premium,
        cost_of_debt=cost_of_debt,
        market_cap=md.market_cap,
        total_cash=total_cash,
        shares_outstanding=md.shares_outstanding,
        total_debt=total_debt,
        tax_rate=a.tax_rate,
        long_term_growth_rate=sd.long_term_growth_rate,
        falled_back_to_risk_free_rate=falled_back_to_risk_free_rate,
    )


def project_revenue(base: float, growth: float, years: int) -> list[float]:
    """Compound revenue forward from base year."""
    return [base * (1 + growth) ** y for y in range(1, years + 1)]


def project_revenue_path(base: float, growth_path: list[float]) -> list[float]:
    """Compound revenue along a per-year growth path (e.g. a fade), not a flat rate."""
    revenue = []
    level = base
    for g in growth_path:
        level *= 1 + g
        revenue.append(level)
    return revenue


def project_income_statement(
    revenue: list[float],
    ebit_margin: float,
    tax_rate: float,
) -> dict[str, list[float]]:
    """
    Project EBIT, tax, and EBIAT from revenue series.
    Returns {"ebit": [...], "tax": [...], "ebiat": [...]}
    """
    ebit  = [r * ebit_margin for r in revenue]
    tax   = [e * tax_rate    for e in ebit]
    ebiat = [e - t           for e, t in zip(ebit, tax)]
    return {"ebit": ebit, "tax": tax, "ebiat": ebiat}


def project_da_capex(
    revenue: list[float],
    da_pct: float,
    capex_pct: float,
) -> dict[str, list[float]]:
    """
    Project D&A and CapEx as % of revenue.
    Returns {"da": [...], "capex": [...]}
    """
    da    = [r * da_pct    for r in revenue]
    capex = [r * capex_pct for r in revenue]
    return {"da": da, "capex": capex}


def project_delta_nwc(
    revenue: list[float],
    base_rev: float,
    nwc_pct: float,
) -> list[float]:
    """
    ΔNWC = nwc_pct × (revenue_t − revenue_t-1).
    Negative nwc_pct (e.g. AAPL) → negative ΔNWC → adds to UFCF.
    base_rev anchors the first year delta.
    """
    all_rev = [base_rev] + revenue
    return [nwc_pct * (all_rev[i] - all_rev[i - 1]) for i in range(1, len(all_rev))]


def project_ufcf(
    ebiat: list[float],
    da: list[float],
    capex: list[float],
    delta_nwc: list[float],
) -> list[float]:
    """
    UFCF = EBIAT + D&A − CapEx − ΔNWC

    Sign convention:
      capex     > 0 (absolute value, subtracted)
      delta_nwc > 0 means NWC increased (cash outflow, subtracted)
      delta_nwc < 0 means NWC decreased (cash inflow, adds to UFCF)
    """
    return [
        e + d - c - n
        for e, d, c, n in zip(ebiat, da, capex, delta_nwc)
    ]


def run_dcf(
    hf: HistoricalFinancials,
    inputs: ValuationInputs,
    assumptions: Assumptions,
    forecast: ForecastAssumptions | None = None,
) -> DCFOutput:
    """
    Full DCF valuation pipeline.

    Flow:
        project revenue → IS → D&A/CapEx → ΔNWC → UFCF
        → discount at WACC
        → Gordon Growth terminal value
        → bridge to equity
        → intrinsic value per share

    When a `forecast` artifact is given it drives the projection: revenue
    follows its per-year growth fade path instead of the flat rate, terminal
    growth comes from the artifact (clamped below WACC to keep TV finite),
    and the assumption-transparency fields of DCFOutput are populated from
    its provenance.
    """
    base_period = hf.periods[-1]
    base_rev    = base_period.income_statement.revenue
    wacc        = inputs.wacc
    span_years  = len(hf.periods)

    terminal_growth_clamped = False
    if forecast is not None:
        years = len(forecast.revenue_growth_path)
        g_target = forecast.terminal_growth.value
        g = min(g_target, wacc - TERMINAL_WACC_BUFFER)
        terminal_growth_clamped = g != g_target
        span_years = forecast.span_years
        revenue = project_revenue_path(base_rev, forecast.revenue_growth_path)
    else:
        years = inputs.projection_years
        g = inputs.long_term_growth_rate
        revenue = project_revenue(base_rev, assumptions.revenue_growth, years)

    # 1. Project
    is_proj   = project_income_statement(revenue, assumptions.ebit_margin, assumptions.tax_rate)
    da_capex  = project_da_capex(
                    revenue,
                    assumptions.depreciation_and_amortization_over_revenue,
                    assumptions.capex_over_revenue,
                )
    delta_nwc = project_delta_nwc(revenue, base_rev, assumptions.nwc_over_revenue)
    ufcf      = project_ufcf(is_proj["ebiat"], da_capex["da"], da_capex["capex"], delta_nwc)
 
    # 2. Discount
    pv_factors = [1 / (1 + wacc) ** t for t in range(1, years + 1)]
    pv_ufcf    = [u * f for u, f in zip(ufcf, pv_factors)]
 
    # 3. Terminal value (Gordon Growth)
    terminal_value = ufcf[-1] * (1 + g) / (wacc - g)
    pv_terminal    = terminal_value * pv_factors[-1]
 
    # 4. Bridge to equity
    enterprise_value          = sum(pv_ufcf) + pv_terminal
    equity_value              = enterprise_value - inputs.total_debt + inputs.total_cash
    intrinsic_value_per_share = equity_value / inputs.shares_outstanding
 
    base_fy      = base_period.fiscal_year or str(base_period.period_end.year)
    base_year    = int(base_fy.replace("FY", ""))
    projection_years = [f"FY{base_year + i + 1}" for i in range(years)]
    tv_pct_of_ev = pv_terminal / enterprise_value

    return DCFOutput(
            ticker=hf.ticker,
            fiscal_year=base_fy,
            projection_years=projection_years,
            intrinsic_value_per_share=intrinsic_value_per_share,
            enterprise_value=enterprise_value,
            equity_value=equity_value,
            terminal_value=terminal_value,
            pv_terminal=pv_terminal,
            tv_pct_of_ev=tv_pct_of_ev,
            projected_revenue=revenue,
            projected_ebit=is_proj["ebit"],
            projected_ebiat=is_proj["ebiat"],
            projected_da=da_capex["da"],
            projected_capex=da_capex["capex"],
            projected_delta_nwc=delta_nwc,
            projected_fcff=ufcf,
            pv_factors=pv_factors,
            pv_fcff=pv_ufcf,
            falled_back_to_risk_free_rate=inputs.falled_back_to_risk_free_rate,
            # ── WACC + components ──
            wacc=wacc,
            terminal_growth=g,
            cost_of_debt=getattr(inputs, "cost_of_debt", None),
            cost_of_equity=getattr(inputs, "cost_of_capital", None),
            risk_free_rate=getattr(inputs, "risk_free_rate", None),
            equity_risk_premium=getattr(inputs, "equity_risk_premium", None),
            beta=getattr(inputs, "beta", None),
            tax_rate=getattr(assumptions, "tax_rate", None),
            equity_weight=getattr(inputs, "equity_weight", None),
            debt_weight=getattr(inputs, "debt_weight", None),
            # Projection assumptions: flat rates averaged over span_years of
            # history, applied identically to every projected year.
            assumption_span_years=span_years,
            assumption_revenue_growth=assumptions.revenue_growth,
            assumption_ebit_margin=assumptions.ebit_margin,
            assumption_da_over_revenue=assumptions.depreciation_and_amortization_over_revenue,
            assumption_capex_over_revenue=assumptions.capex_over_revenue,
            assumption_nwc_over_revenue=assumptions.nwc_over_revenue,
            # ── Assumption transparency (forecast-driven runs only) ──
            projected_growth_path=(list(forecast.revenue_growth_path) if forecast else None),
            terminal_growth_clamped=terminal_growth_clamped,
            assumption_provenance=(
                {name: getattr(forecast, name).model_dump() for name in _FORECAST_DRIVERS}
                if forecast else None
            ),
            assumption_quality_flags=(list(forecast.quality_flags) if forecast else []),
            assumption_missing_inputs=(list(forecast.missing_inputs) if forecast else []),
        )