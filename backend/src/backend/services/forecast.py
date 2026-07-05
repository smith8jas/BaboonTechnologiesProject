"""Forecast assumption engine: context-aware, provenance-tracked projection drivers.

Builds a ForecastAssumptions artifact from whatever inputs are available and
records, per assumption, how it was derived and what was missing. Degradation
ladder (best method available wins):

    market/sector context + history  →  size-capped growth with fade to the
                                        sector terminal rate
    history only                     →  recency-weighted robust averages with
                                        fade to the default terminal rate
    thin history                     →  same, flagged low-confidence
    nothing usable                   →  conservative defaults, flagged

Every numeric decision (weights, clamps, size caps) lives in module constants
so future producers — including agent-based simulations — can reuse or replace
individual pieces while emitting the same artifact shape.
"""

from __future__ import annotations

from statistics import median

from backend.processing.schema import (
    AssumptionProvenance,
    ForecastAssumptions,
    HistoricalFinancials,
    MarketData,
    SectorData,
)

# ── Tunable heuristics ───────────────────────────────────────────────────────

DEFAULT_TERMINAL_GROWTH = 0.025          # GDP-proxy floor when sector data is absent
DEFAULT_TAX_RATE = 0.21                  # US statutory fallback
MAD_OUTLIER_THRESHOLD = 3.0              # exclude points beyond 3×MAD from the median (n ≥ 4)
MIN_PERIODS_FOR_OUTLIER_FILTER = 4

# Initial revenue-growth cap by company size (market cap, USD). Large companies
# rarely sustain small-company growth; without market data no cap is applied
# and that limitation is recorded.
SIZE_GROWTH_CAPS: list[tuple[float, str, float]] = [
    (200e9, "mega_cap", 0.12),
    (10e9,  "large_cap", 0.20),
    (2e9,   "mid_cap",  0.30),
    (0.0,   "small_cap", 0.50),
]

# Sanity clamps per driver: (low, high)
CLAMPS: dict[str, tuple[float, float]] = {
    "revenue_growth":    (-0.15, 0.50),  # high end further capped by size
    "ebit_margin":       (-0.30, 0.60),
    "tax_rate":          (0.00, 0.50),
    "da_over_revenue":   (0.00, 0.25),
    "capex_over_revenue": (0.00, 0.40),
    "nwc_over_revenue":  (-0.30, 0.30),
    "terminal_growth":   (0.00, 0.04),
}

_OVERRIDABLE = {
    "revenue_growth", "ebit_margin", "tax_rate",
    "da_over_revenue", "capex_over_revenue", "nwc_over_revenue",
    "terminal_growth",
}


def build_forecast_assumptions(
    hf: HistoricalFinancials,
    md: MarketData | None = None,
    sd: SectorData | None = None,
    *,
    industry: str | None = None,
    overrides: dict[str, float] | None = None,
    projection_years: int = 5,
    scenario: str = "default",
) -> ForecastAssumptions:
    """Derive projection drivers from history plus whatever context exists."""
    periods = hf.periods
    span = len(periods)
    overrides = overrides or {}
    quality_flags: list[str] = []

    history_input = f"financials:{span}y"
    if span < 3:
        quality_flags.append("short_history")

    industry_label = industry or hf.metadata.industry
    context_inputs = [history_input]
    if industry_label:
        context_inputs.append(f"industry:{industry_label}")

    # ── Historical series ────────────────────────────────────────────────
    rev = [p.income_statement.revenue for p in periods]
    growth_series = [
        (rev[i] - rev[i - 1]) / abs(rev[i - 1])
        for i in range(1, len(rev))
        if rev[i] is not None and rev[i - 1]
    ]
    margin_series = [
        p.income_statement.ebit / p.income_statement.revenue
        for p in periods
        if p.income_statement.ebit is not None and p.income_statement.revenue
    ]
    tax_series = [
        p.income_statement.tax_expense / p.income_statement.ebit
        for p in periods
        # positive-EBIT years only: tax/EBIT is meaningless in loss years
        if p.income_statement.tax_expense is not None
        and p.income_statement.ebit and p.income_statement.ebit > 0
    ]
    da_series = [
        p.cash_flow.depreciation_amortization / p.income_statement.revenue
        for p in periods
        if p.cash_flow.depreciation_amortization is not None and p.income_statement.revenue
    ]
    capex_series = [
        abs(p.cash_flow.capex) / p.income_statement.revenue
        for p in periods
        if p.cash_flow.capex is not None and p.income_statement.revenue
    ]
    nwc_series = [
        p.balance_sheet.net_working_capital / p.income_statement.revenue
        for p in periods
        if p.balance_sheet.net_working_capital is not None and p.income_statement.revenue
    ]

    # ── Terminal growth (anchor for the fade) ────────────────────────────
    if "terminal_growth" in overrides:
        terminal = _override("terminal_growth", overrides["terminal_growth"])
    elif sd is not None and sd.long_term_growth_rate is not None:
        value, clamped = clamp_driver("terminal_growth", sd.long_term_growth_rate)
        terminal = AssumptionProvenance(
            value=value,
            method="sector_anchor",
            inputs_used=["sector_data:long_term_growth_rate"],
            rationale="Sector long-term growth rate used as the terminal anchor.",
            confidence="high" if not clamped else "medium",
        )
        if clamped:
            quality_flags.append("clamped:terminal_growth")
    else:
        terminal = AssumptionProvenance(
            value=DEFAULT_TERMINAL_GROWTH,
            method="default",
            inputs_used=[],
            missing_inputs=["sector_data:long_term_growth_rate"],
            rationale=f"No sector data available — defaulted to the {DEFAULT_TERMINAL_GROWTH:.1%} GDP-proxy terminal rate.",
            confidence="low",
        )

    # ── Revenue growth: robust history, size-capped, faded to terminal ───
    if "revenue_growth" in overrides:
        growth = _override("revenue_growth", overrides["revenue_growth"])
    else:
        growth = _series_assumption(
            "revenue_growth", growth_series, context_inputs, quality_flags,
            missing_hint="income_statement.revenue (consecutive periods)",
            what="year-over-year revenue growth",
        )
        growth = _apply_size_cap(growth, md, quality_flags)

    growth_path = fade_path(growth.value, terminal.value, projection_years)

    # ── Remaining drivers ─────────────────────────────────────────────────
    def _driver(name: str, series: list[float], missing_hint: str, what: str) -> AssumptionProvenance:
        if name in overrides:
            return _override(name, overrides[name])
        return _series_assumption(name, series, context_inputs, quality_flags,
                                  missing_hint=missing_hint, what=what)

    margin = _driver("ebit_margin", margin_series,
                     "income_statement.ebit and revenue", "EBIT margin")
    da_pct = _driver("da_over_revenue", da_series,
                     "cash_flow.depreciation_amortization",
                     "D&A as % of revenue")
    capex_pct = _driver("capex_over_revenue", capex_series,
                        "cash_flow.capex", "CapEx as % of revenue")
    nwc_pct = _driver("nwc_over_revenue", nwc_series,
                      "balance_sheet.net_working_capital", "NWC as % of revenue")

    if "tax_rate" in overrides:
        tax = _override("tax_rate", overrides["tax_rate"])
    elif tax_series:
        tax = _series_assumption("tax_rate", tax_series, context_inputs, quality_flags,
                                 missing_hint="", what="effective tax rate (positive-EBIT years)")
    else:
        tax = AssumptionProvenance(
            value=DEFAULT_TAX_RATE,
            method="default",
            missing_inputs=["income_statement.tax_expense with positive ebit"],
            rationale=f"No usable effective-tax history — defaulted to the {DEFAULT_TAX_RATE:.0%} statutory rate.",
            confidence="low",
        )
        quality_flags.append("default:tax_rate")

    if not da_series:
        quality_flags.append("da_missing_understates_ufcf")

    drivers = {
        "revenue_growth": growth, "ebit_margin": margin, "tax_rate": tax,
        "da_over_revenue": da_pct, "capex_over_revenue": capex_pct,
        "nwc_over_revenue": nwc_pct, "terminal_growth": terminal,
    }
    missing = sorted({m for d in drivers.values() for m in d.missing_inputs})

    return ForecastAssumptions(
        ticker=hf.ticker,
        scenario=scenario,
        span_years=span,
        projection_years=projection_years,
        revenue_growth=growth,
        revenue_growth_path=growth_path,
        ebit_margin=margin,
        tax_rate=tax,
        da_over_revenue=da_pct,
        capex_over_revenue=capex_pct,
        nwc_over_revenue=nwc_pct,
        terminal_growth=terminal,
        quality_flags=sorted(set(quality_flags)),
        missing_inputs=missing,
    )


# ── Building blocks ──────────────────────────────────────────────────────────

def _series_assumption(
    name: str,
    series: list[float],
    context_inputs: list[str],
    quality_flags: list[str],
    *,
    missing_hint: str,
    what: str,
) -> AssumptionProvenance:
    """Recency-weighted robust average of a historical ratio series."""
    if not series:
        low, high = CLAMPS[name]
        value = min(max(0.0, low), high)
        quality_flags.append(f"default:{name}")
        return AssumptionProvenance(
            value=value,
            method="default",
            missing_inputs=[missing_hint] if missing_hint else [],
            rationale=f"No historical data to estimate {what} — defaulted to {value:.1%}.",
            confidence="low",
        )

    kept, excluded = _filter_outliers(series)
    if excluded:
        quality_flags.append(f"outliers_excluded:{name}")

    raw = _recency_weighted_avg(kept)
    value, clamped = clamp_driver(name, raw)
    if clamped:
        quality_flags.append(f"clamped:{name}")

    n = len(kept)
    confidence = "high" if n >= 4 and not excluded and not clamped else ("low" if n <= 1 else "medium")
    rationale = (
        f"Recency-weighted average of {what} over {n} historical point(s)"
        + (f", {excluded} outlier(s) excluded" if excluded else "")
        + (f", clamped from {raw:.1%} to {value:.1%}" if clamped else "")
        + "."
    )
    return AssumptionProvenance(
        value=value,
        method="weighted_history",
        inputs_used=list(context_inputs),
        missing_inputs=[],
        rationale=rationale,
        confidence=confidence,
    )


def _apply_size_cap(
    growth: AssumptionProvenance, md: MarketData | None, quality_flags: list[str]
) -> AssumptionProvenance:
    """Cap initial growth by company size — large companies rarely compound like small ones."""
    if md is None or md.market_cap is None:
        growth.missing_inputs = [*growth.missing_inputs, "market_data:market_cap (size-based growth cap)"]
        return growth

    for floor, label, cap in SIZE_GROWTH_CAPS:
        if md.market_cap >= floor:
            growth.inputs_used = [*growth.inputs_used, f"market_data:market_cap ({label})"]
            if growth.value > cap:
                quality_flags.append("size_capped:revenue_growth")
                return AssumptionProvenance(
                    value=cap,
                    method="size_capped_fade",
                    inputs_used=growth.inputs_used,
                    missing_inputs=growth.missing_inputs,
                    rationale=growth.rationale.rstrip(".")
                    + f"; capped at {cap:.0%} for a {label.replace('_', ' ')} company.",
                    confidence=growth.confidence,
                )
            return growth
    return growth


def fade_path(initial: float, terminal: float, years: int) -> list[float]:
    """Linear convergence from initial growth to the terminal rate.

    Ends one step short of the terminal rate so the Gordon Growth transition
    stays smooth (last projected year ≈ but not equal to g). Public: scenario
    producers rebuild the path after shifting growth or terminal drivers.
    """
    if years <= 1:
        return [initial]
    step = (terminal - initial) / years
    return [initial + step * t for t in range(years)]


def _override(name: str, value: float) -> AssumptionProvenance:
    if name not in _OVERRIDABLE:
        raise ValueError(f"Unknown assumption override: {name}")
    clamped_value, clamped = clamp_driver(name, float(value))
    return AssumptionProvenance(
        value=clamped_value,
        method="override",
        inputs_used=["caller_override"],
        rationale="Explicitly provided by the caller"
        + (f" (clamped from {float(value):.1%} to {clamped_value:.1%})" if clamped else "")
        + ".",
        confidence="high",
    )


def clamp_driver(name: str, value: float) -> tuple[float, bool]:
    """Clamp a driver value to its sanity range; public for scenario producers."""
    low, high = CLAMPS[name]
    clamped = min(max(value, low), high)
    return clamped, clamped != value


def _filter_outliers(series: list[float]) -> tuple[list[float], int]:
    """Drop points beyond MAD_OUTLIER_THRESHOLD×MAD from the median (n ≥ 4)."""
    if len(series) < MIN_PERIODS_FOR_OUTLIER_FILTER:
        return list(series), 0
    med = median(series)
    mad = median(abs(x - med) for x in series)
    if mad == 0:
        return list(series), 0
    kept = [x for x in series if abs(x - med) <= MAD_OUTLIER_THRESHOLD * mad]
    return kept, len(series) - len(kept)


def _recency_weighted_avg(series: list[float]) -> float:
    """Linear recency weights: the most recent point counts n times the oldest."""
    weights = range(1, len(series) + 1)
    return sum(w * x for w, x in zip(weights, series)) / sum(weights)
