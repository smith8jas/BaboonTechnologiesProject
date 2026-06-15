"""CLI harness: run full DCF pipeline and print step-by-step results."""

import sys
from datetime import date

from backend.services.financials import get_financials, get_market_data, get_sector_data
from backend.services.dcf_engine import build_assumptions, build_valuation_inputs, run_dcf


def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: uv run python -m backend.scripts.dcf [TICKER]")

    TICKER = sys.argv[-1]

    # ── 1. Fetch ──────────────────────────────────────────────────────────
    section("1. Fetching data")
    hf = get_financials(TICKER, 5)
    md = get_market_data(TICKER)
    sd = get_sector_data(date.today().year)
    print(f"  {hf.metadata.name}  ({hf.metadata.industry})")
    print(f"  {len(hf.periods)} periods: {hf.periods[0].fiscal_year} → {hf.periods[-1].fiscal_year}")

    # ── 2. Assumptions ────────────────────────────────────────────────────
    section("2. Assumptions (trailing averages)")
    a = build_assumptions(hf)
    print(f"  {'Revenue growth:':<26} {fmt_pct(a.revenue_growth)}")
    print(f"  {'EBIT margin:':<26} {fmt_pct(a.ebit_margin)}")
    print(f"  {'Tax rate:':<26} {fmt_pct(a.tax_rate)}")
    print(f"  {'D&A / revenue:':<26} {fmt_pct(a.depreciation_and_amortization_over_revenue)}")
    print(f"  {'CapEx / revenue:':<26} {fmt_pct(a.capex_over_revenue)}")
    print(f"  {'NWC / revenue:':<26} {fmt_pct(a.nwc_over_revenue)}")

    # ── 3. Valuation inputs ───────────────────────────────────────────────
    section("3. Valuation Inputs")
    vi = build_valuation_inputs(hf, md, sd, a)
    print(f"  {'Beta:':<26} {vi.beta:.3f}")
    print(f"  {'Risk-free rate:':<26} {fmt_pct(vi.risk_free_rate)}")
    print(f"  {'ERP:':<26} {fmt_pct(vi.equity_risk_premium)}")
    print(f"  {'Cost of equity:':<26} {fmt_pct(vi.cost_of_capital)}")
    print(f"  {'Cost of debt:':<26} {fmt_pct(vi.cost_of_debt)}")
    print(f"  {'WACC:':<26} {fmt_pct(vi.wacc)}")
    print(f"  {'Terminal growth:':<26} {fmt_pct(vi.long_term_growth_rate)}")
    print(f"  {'Total debt:':<26} {vi.total_debt/1e9:,.2f}B")
    print(f"  {'Shares outstanding:':<26} {vi.shares_outstanding/1e9:,.2f}B")

    # ── Run ───────────────────────────────────────────────────────────────
    r = run_dcf(hf, vi, a)

    # ── 4. Projections ────────────────────────────────────────────────────
    section("4. Projections ($B)")
    print(f"  {'':8} {'Revenue':>10} {'EBIT':>10} {'EBIAT':>10} {'D&A':>8} {'CapEx':>8} {'ΔNWC':>8} {'UFCF':>10}")
    print(f"  {'-'*80}")
    for i, fy in enumerate(r.projection_years):
        print(
            f"  {fy:<8} "
            f"{r.projected_revenue[i]/1e9:>10,.1f} "
            f"{r.projected_ebit[i]/1e9:>10,.1f} "
            f"{r.projected_ebiat[i]/1e9:>10,.1f} "
            f"{r.projected_da[i]/1e9:>8,.1f} "
            f"{r.projected_capex[i]/1e9:>8,.1f} "
            f"{r.projected_delta_nwc[i]/1e9:>8,.1f} "
            f"{r.projected_fcff[i]/1e9:>10,.1f}"
        )

    # ── 5. Discounting ────────────────────────────────────────────────────
    section("5. Discounting ($B)")
    print(f"  {'':8} {'PV factor':>10} {'PV(UFCF)':>10}")
    print(f"  {'-'*32}")
    for i, fy in enumerate(r.projection_years):
        print(f"  {fy:<8} {r.pv_factors[i]:>10.4f} {r.pv_fcff[i]/1e9:>10,.1f}")
    print(f"  {'Sum PV(UFCF):':<18} {sum(r.pv_fcff)/1e9:>10,.1f}B")

    # ── 6. Terminal value ─────────────────────────────────────────────────
    section("6. Terminal Value")
    print(f"  {'Terminal value:':<26} {r.terminal_value/1e9:>10,.1f}B")
    print(f"  {'PV(TV):':<26} {r.pv_terminal/1e9:>10,.1f}B")
    print(f"  {'TV % of EV:':<26} {r.tv_pct_of_ev:>9.1%}")

    # ── 7. Valuation bridge ───────────────────────────────────────────────
    section("7. Valuation Bridge")
    updown = r.intrinsic_value_per_share / md.current_price - 1
    print(f"  {'Enterprise value:':<26} {r.enterprise_value/1e9:>10,.1f}B")
    print(f"  {'Less: total debt:':<26} {vi.total_debt/1e9:>10,.1f}B")
    print(f"  {'Equity value:':<26} {r.equity_value/1e9:>10,.1f}B")
    print(f"  {'Shares outstanding:':<26} {vi.shares_outstanding/1e9:>10,.2f}B")
    print(f"  {'─'*40}")
    print(f"  {'Intrinsic value/share:':<26} ${r.intrinsic_value_per_share:>9,.2f}")
    print(f"  {'Market price:':<26} ${md.current_price:>9,.2f}")
    print(f"  {'Upside/(Downside):':<26} {updown:>9.1%}")
    print()


# ── Helpers ──────────────────────────────────────────────────────────────────

def fmt_pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v:>7.2%}"

def section(title: str) -> None:
    print(f"\n{'─' * 64}")
    print(f"  {title}")
    print(f"{'─' * 64}")


if __name__ == "__main__":
    main()