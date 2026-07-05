"""Unit tests for the scenario service and the forecast-driven DCF path.

Covers:
- bear/base/bull derivation: labels, driver shifts, provenance, clamping
- fade-path rebuild after a scenario shift
- run_dcf with a forecast artifact: path-based revenue, terminal clamp below
  WACC, and the assumption-transparency fields of DCFOutput
- run_dcf without a forecast keeping its original behavior
- end-to-end scenario valuation ordering (bear < base < bull)
- run_scenario_analysis tool registration and cache-miss contract
"""

import pytest

from backend.agent.cache import CacheMissError
from backend.agent.tools import TOOLS_BY_NAME
from backend.agent.tools.base import PHASE_CALCULATION
from backend.processing.schema import Assumptions, HistoricalFinancials, MarketData, SectorData
from backend.services import dcf_engine, scenarios
from backend.services.forecast import build_forecast_assumptions

# ── Fixtures ─────────────────────────────────────────────────────────────────


def _hf(ticker: str = "TEST", years: int = 5) -> HistoricalFinancials:
    """Steady company: 10% growth, 20% EBIT margin, 21% tax, 5% capex, 4% D&A, 10% NWC."""
    periods = []
    revenue = 100.0
    for i in range(years):
        year = 2020 + i
        ebit = revenue * 0.20
        periods.append({
            "fiscal_year": f"FY{year}",
            "period_end": f"{year}-12-31",
            "income_statement": {
                "revenue": revenue,
                "ebit": ebit,
                "tax_expense": ebit * 0.21,
                "net_income": ebit * 0.79,
            },
            "balance_sheet": {
                "total_current_assets": revenue * 0.30,
                "total_current_liabilities": revenue * 0.20,
                "cash": revenue * 0.10,
            },
            "cash_flow": {
                "capex": revenue * 0.05,
                "depreciation_amortization": revenue * 0.04,
            },
            "per_share": {},
        })
        revenue *= 1.10
    return HistoricalFinancials.model_validate({
        "ticker": ticker,
        "metadata": {"cik": "0000000001", "name": f"{ticker} Inc.", "industry": "Software"},
        "periods": periods,
    })


def _md(**overrides) -> MarketData:
    values = {
        "current_price": 50.0,
        "beta": 1.0,
        "shares_outstanding": 10.0,
        "market_cap": 5e9,
        "risk_free_rate": 0.04,
    }
    values.update(overrides)
    return MarketData.model_validate(values)


def _sd(**overrides) -> SectorData:
    values = {"equity_risk_premium": 0.05, "long_term_growth_rate": 0.025}
    values.update(overrides)
    return SectorData.model_validate(values)


# ── Scenario derivation ──────────────────────────────────────────────────────


def test_build_scenarios_labels_and_driver_shifts():
    result = scenarios.build_scenarios(_hf(), _md(), _sd())

    assert set(result) == {"bear", "base", "bull"}
    for name, fa in result.items():
        assert fa.scenario == name

    base_growth = result["base"].revenue_growth.value
    assert result["bear"].revenue_growth.value == pytest.approx(base_growth - 0.05)
    assert result["bull"].revenue_growth.value == pytest.approx(base_growth + 0.05)
    # unshifted drivers stay at base
    assert result["bear"].tax_rate.value == result["base"].tax_rate.value
    assert result["bull"].nwc_over_revenue.value == result["base"].nwc_over_revenue.value


def test_derive_scenario_provenance_and_fade_path():
    base = build_forecast_assumptions(_hf(), _md(), _sd(), scenario="base")
    bear = scenarios.derive_scenario(base, "bear")

    prov = bear.revenue_growth
    assert prov.method == "scenario_shift"
    assert "scenario_shift:bear" in prov.inputs_used
    assert "bear scenario" in prov.rationale

    # path rebuilt from the shifted drivers: starts at bear growth, fades
    # toward bear terminal, and differs from the base path
    assert bear.revenue_growth_path[0] == pytest.approx(bear.revenue_growth.value)
    assert bear.revenue_growth_path != base.revenue_growth_path
    assert len(bear.revenue_growth_path) == base.projection_years
    assert bear.revenue_growth_path[-1] > bear.terminal_growth.value


def test_derive_scenario_clamps_and_flags():
    base = build_forecast_assumptions(
        _hf(), _md(), _sd(), overrides={"capex_over_revenue": 0.005}, scenario="base"
    )
    bull = scenarios.derive_scenario(base, "bull")  # 0.005 − 0.01 → clamped to 0.0

    assert bull.capex_over_revenue.value == 0.0
    assert "clamped:bull:capex_over_revenue" in bull.quality_flags


# ── Forecast-driven DCF ──────────────────────────────────────────────────────


def test_run_dcf_with_forecast_uses_path_and_populates_transparency():
    hf, md, sd = _hf(), _md(), _sd()
    fa = build_forecast_assumptions(hf, md, sd, scenario="base")
    assumptions = fa.to_assumptions()
    inputs = dcf_engine.build_valuation_inputs(hf, md, sd, assumptions)

    dcf = dcf_engine.run_dcf(hf, inputs, assumptions, forecast=fa)

    assert dcf.projected_growth_path == fa.revenue_growth_path
    base_rev = hf.periods[-1].income_statement.revenue
    assert dcf.projected_revenue[0] == pytest.approx(base_rev * (1 + fa.revenue_growth_path[0]))
    assert set(dcf.assumption_provenance) == {
        "revenue_growth", "ebit_margin", "tax_rate", "da_over_revenue",
        "capex_over_revenue", "nwc_over_revenue", "terminal_growth",
    }
    assert dcf.terminal_growth == pytest.approx(fa.terminal_growth.value)
    assert dcf.terminal_growth_clamped is False
    assert dcf.assumption_span_years == fa.span_years


def test_run_dcf_without_forecast_keeps_original_behavior():
    """Flat-rate path stays supported for callers that pass plain Assumptions."""
    hf, md, sd = _hf(), _md(), _sd()
    assumptions = Assumptions(
        revenue_growth=0.10, ebit_margin=0.20, tax_rate=0.21,
        depreciation_and_amortization_over_revenue=0.04,
        capex_over_revenue=0.05, nwc_over_revenue=0.10,
    )
    inputs = dcf_engine.build_valuation_inputs(hf, md, sd, assumptions)

    dcf = dcf_engine.run_dcf(hf, inputs, assumptions)

    assert dcf.projected_growth_path is None
    assert dcf.assumption_provenance is None
    assert dcf.terminal_growth_clamped is False
    # flat growth: every projected year compounds at the same rate
    g = assumptions.revenue_growth
    base_rev = hf.periods[-1].income_statement.revenue
    assert dcf.projected_revenue[0] == pytest.approx(base_rev * (1 + g))
    assert dcf.projected_revenue[1] == pytest.approx(base_rev * (1 + g) ** 2)


def test_run_dcf_clamps_terminal_growth_below_wacc():
    hf = _hf()
    md = _md(beta=0.1, risk_free_rate=0.02)   # WACC = 0.02 + 0.1×0.05 = 2.5%
    sd = _sd(long_term_growth_rate=0.04)      # terminal anchor above WACC
    fa = build_forecast_assumptions(hf, md, sd, scenario="base")
    assumptions = fa.to_assumptions()

    with pytest.warns(UserWarning):           # schema warns WACC < long-term growth
        inputs = dcf_engine.build_valuation_inputs(hf, md, sd, assumptions)

    dcf = dcf_engine.run_dcf(hf, inputs, assumptions, forecast=fa)

    assert dcf.terminal_growth_clamped is True
    assert dcf.terminal_growth == pytest.approx(inputs.wacc - dcf_engine.TERMINAL_WACC_BUFFER)
    assert dcf.terminal_value > 0


# ── End-to-end scenario valuation ────────────────────────────────────────────


def test_run_scenario_analysis_orders_valuations():
    result = scenarios.run_scenario_analysis(_hf(), _md(), _sd())

    per_share = {name: result["scenarios"][name]["intrinsic_value_per_share"]
                 for name in ("bear", "base", "bull")}
    assert per_share["bear"] < per_share["base"] < per_share["bull"]
    assert result["valuation_range"]["low"] == per_share["bear"]
    assert result["valuation_range"]["base"] == per_share["base"]
    assert result["valuation_range"]["high"] == per_share["bull"]

    for name, summary in result["scenarios"].items():
        assert summary["scenario"] == name
        assert len(summary["revenue_growth_path"]) == result["projection_years"]
        for driver in summary["assumptions"].values():
            assert driver["rationale"]
            assert driver["confidence"] in {"high", "medium", "low"}


# ── Tool registration and contract ───────────────────────────────────────────


def test_scenario_tool_registered_with_calculation_phase():
    tool = TOOLS_BY_NAME["run_scenario_analysis"]
    agent_meta = tool.metadata["agent"]
    assert agent_meta["phase"] == PHASE_CALCULATION
    assert agent_meta["group"] == "scenario"

    from backend.agent.streaming import GROUP_LABELS
    assert "scenario" in GROUP_LABELS


def test_scenario_tool_requires_cached_prerequisites():
    tool = TOOLS_BY_NAME["run_scenario_analysis"]
    with pytest.raises(CacheMissError):
        tool.invoke({
            "ticker": "TEST", "span": 5, "year": 2024,
            "research_messages": [], "calculated_messages": [], "cycle": 1,
        })


def test_scenario_tool_writes_scenarios_cache_entry():
    hf, md, sd = _hf(), _md(), _sd()
    research_messages = [
        {"tool": "get_financials", "identifier": ("financials", "TEST"), "ticker": "TEST",
         "cycle": 1, "last_updated": "", "data": hf.model_dump(mode="json"), "data_source": "t"},
        {"tool": "get_market_data", "identifier": ("market_data", "TEST"), "ticker": "TEST",
         "cycle": 1, "last_updated": "", "data": md.model_dump(mode="json"), "data_source": "t"},
        {"tool": "get_sector_data", "identifier": ("sector_data", 2024), "ticker": None,
         "cycle": 1, "last_updated": "", "data": sd.model_dump(mode="json"), "data_source": "t"},
    ]
    calculated_messages: list = []

    result = TOOLS_BY_NAME["run_scenario_analysis"].invoke({
        "ticker": "test", "span": 5, "year": 2024,
        "research_messages": research_messages,
        "calculated_messages": calculated_messages, "cycle": 1,
    })

    assert result["source"] == "calculated"
    assert [e["identifier"] for e in calculated_messages] == [("scenarios", "TEST")]
    band = result["data"]["valuation_range"]
    assert band["low"] < band["base"] < band["high"]


def test_dcf_tool_point_estimate_matches_scenario_base():
    """run_dcf_valuation consumes the same forecast engine as the scenario
    tool, so its intrinsic value must equal the base scenario's."""
    hf, md, sd = _hf(), _md(), _sd()
    research_messages = [
        {"tool": "get_financials", "identifier": ("financials", "TEST"), "ticker": "TEST",
         "cycle": 1, "last_updated": "", "data": hf.model_dump(mode="json"), "data_source": "t"},
        {"tool": "get_market_data", "identifier": ("market_data", "TEST"), "ticker": "TEST",
         "cycle": 1, "last_updated": "", "data": md.model_dump(mode="json"), "data_source": "t"},
        {"tool": "get_sector_data", "identifier": ("sector_data", 2024), "ticker": None,
         "cycle": 1, "last_updated": "", "data": sd.model_dump(mode="json"), "data_source": "t"},
    ]

    dcf = TOOLS_BY_NAME["run_dcf_valuation"].invoke({
        "ticker": "TEST", "span": 5, "year": 2024,
        "research_messages": research_messages, "calculated_messages": [], "cycle": 1,
    })
    scen = TOOLS_BY_NAME["run_scenario_analysis"].invoke({
        "ticker": "TEST", "span": 5, "year": 2024,
        "research_messages": research_messages, "calculated_messages": [], "cycle": 1,
    })

    assert dcf["data"]["intrinsic_value_per_share"] == pytest.approx(
        scen["data"]["valuation_range"]["base"]
    )
    # forecast-driven run: fade path and provenance are populated
    assert dcf["data"]["projected_growth_path"]
    assert dcf["data"]["assumption_provenance"]["revenue_growth"]["method"]
