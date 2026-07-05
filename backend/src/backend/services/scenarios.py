"""Scenario service: bear / base / bull DCF analysis over forecast artifacts.

The base scenario is the deterministic forecast engine's ForecastAssumptions
(recency-weighted history, sector/size context, full provenance). Bear and
bull apply the documented driver shifts below, re-clamp through the forecast
engine's sanity ranges, rebuild the growth fade path, and re-value through
the DCF engine — so every scenario figure is a computed model output with an
audit trail, never an extrapolation.

Shifts are deliberate model policy, not predictions: they answer "what is the
valuation impact if drivers land this much worse/better than the base
estimate". They are asymmetric on purpose — margins compress faster than they
expand, and capex overruns are more common than savings. Future producers
(e.g. agent-based simulations deriving probabilities from scraped narrative)
can replace SCENARIO_SHIFTS while emitting the same artifact shape.
"""

from __future__ import annotations

from backend.processing.schema import (
    AssumptionProvenance,
    DCFOutput,
    ForecastAssumptions,
    HistoricalFinancials,
    MarketData,
    SectorData,
)
from backend.services import dcf_engine
from backend.services.forecast import build_forecast_assumptions, clamp_driver, fade_path

SCENARIO_BEAR = "bear"
SCENARIO_BASE = "base"
SCENARIO_BULL = "bull"
SCENARIO_ORDER: tuple[str, ...] = (SCENARIO_BEAR, SCENARIO_BASE, SCENARIO_BULL)

# Additive shifts (percentage points) applied to the base drivers. Drivers not
# listed (tax_rate, da_over_revenue, nwc_over_revenue) are held at base — the
# scenarios isolate the operating levers that dominate DCF outcomes.
SCENARIO_SHIFTS: dict[str, dict[str, float]] = {
    SCENARIO_BEAR: {
        "revenue_growth":     -0.05,
        "ebit_margin":        -0.03,
        "capex_over_revenue": +0.02,
        "terminal_growth":    -0.005,
    },
    SCENARIO_BULL: {
        "revenue_growth":     +0.05,
        "ebit_margin":        +0.02,
        "capex_over_revenue": -0.01,
        "terminal_growth":    +0.005,
    },
}

_DRIVER_NAMES = (
    "revenue_growth", "ebit_margin", "tax_rate", "da_over_revenue",
    "capex_over_revenue", "nwc_over_revenue", "terminal_growth",
)


def derive_scenario(base: ForecastAssumptions, name: str) -> ForecastAssumptions:
    """Shift the base artifact's drivers per SCENARIO_SHIFTS and rebuild the fade path."""
    shifts = SCENARIO_SHIFTS[name]
    update: dict = {"scenario": name}
    flags = set(base.quality_flags)

    for driver, delta in shifts.items():
        prov: AssumptionProvenance = getattr(base, driver)
        value, clamped = clamp_driver(driver, prov.value + delta)
        if clamped:
            flags.add(f"clamped:{name}:{driver}")
        update[driver] = AssumptionProvenance(
            value=value,
            method="scenario_shift",
            inputs_used=[*prov.inputs_used, f"scenario_shift:{name}"],
            missing_inputs=list(prov.missing_inputs),
            rationale=prov.rationale.rstrip(".")
            + f"; shifted {delta:+.1%} for the {name} scenario"
            + (f" and clamped to {value:.1%}" if clamped else "")
            + ".",
            confidence=prov.confidence,
        )

    growth = update.get("revenue_growth", base.revenue_growth)
    terminal = update.get("terminal_growth", base.terminal_growth)
    update["revenue_growth_path"] = fade_path(growth.value, terminal.value, base.projection_years)
    update["quality_flags"] = sorted(flags)
    return base.model_copy(update=update)


def build_scenarios(
    hf: HistoricalFinancials,
    md: MarketData | None = None,
    sd: SectorData | None = None,
    *,
    industry: str | None = None,
    projection_years: int = 5,
) -> dict[str, ForecastAssumptions]:
    """Base artifact from the forecast engine plus its bear and bull variants."""
    base = build_forecast_assumptions(
        hf, md, sd,
        industry=industry,
        projection_years=projection_years,
        scenario=SCENARIO_BASE,
    )
    return {
        SCENARIO_BEAR: derive_scenario(base, SCENARIO_BEAR),
        SCENARIO_BASE: base,
        SCENARIO_BULL: derive_scenario(base, SCENARIO_BULL),
    }


def run_scenario_analysis(
    hf: HistoricalFinancials,
    md: MarketData,
    sd: SectorData,
    *,
    industry: str | None = None,
    projection_years: int = 5,
) -> dict:
    """Value bear/base/bull through the DCF engine and summarize the range.

    Requires the same inputs as a single DCF run (market data for WACC and the
    equity bridge, sector data for the ERP); the forecast engine handles any
    missing optional fields inside those and records the degradation.
    """
    scenarios = build_scenarios(
        hf, md, sd, industry=industry, projection_years=projection_years
    )

    summaries: dict[str, dict] = {}
    for name in SCENARIO_ORDER:
        fa = scenarios[name]
        assumptions = fa.to_assumptions()
        inputs = dcf_engine.build_valuation_inputs(hf, md, sd, assumptions)
        dcf = dcf_engine.run_dcf(hf, inputs, assumptions, forecast=fa)
        summaries[name] = _scenario_summary(fa, dcf)

    per_share = {name: summaries[name]["intrinsic_value_per_share"] for name in SCENARIO_ORDER}
    base = scenarios[SCENARIO_BASE]
    return {
        "ticker": hf.ticker,
        "projection_years": projection_years,
        "scenarios": summaries,
        "valuation_range": {
            "low": min(per_share.values()),
            "base": per_share[SCENARIO_BASE],
            "high": max(per_share.values()),
        },
        "scenario_shifts": SCENARIO_SHIFTS,
        "quality_flags": base.quality_flags,
        "missing_inputs": base.missing_inputs,
    }


def _scenario_summary(fa: ForecastAssumptions, dcf: DCFOutput) -> dict:
    """Compact per-scenario view: valuation, path, and assumption audit trail."""
    return {
        "scenario": fa.scenario,
        "intrinsic_value_per_share": dcf.intrinsic_value_per_share,
        "enterprise_value": dcf.enterprise_value,
        "equity_value": dcf.equity_value,
        "wacc": dcf.wacc,
        "terminal_growth": dcf.terminal_growth,
        "terminal_growth_clamped": dcf.terminal_growth_clamped,
        "tv_pct_of_ev": dcf.tv_pct_of_ev,
        "revenue_growth_path": fa.revenue_growth_path,
        "projected_revenue": dcf.projected_revenue,
        "projected_fcff": dcf.projected_fcff,
        "assumptions": {
            name: {
                "value": prov.value,
                "method": prov.method,
                "confidence": prov.confidence,
                "rationale": prov.rationale,
            }
            for name in _DRIVER_NAMES
            for prov in [getattr(fa, name)]
        },
        "quality_flags": fa.quality_flags,
    }
