"""CLI harness: fetch and display financials + valuation inputs for a ticker."""

import sys
from datetime import date

from backend.services.financials import get_financials, get_market_data, get_sector_data
from backend.services.dcf_engine import build_assumptions, build_valuation_inputs


def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: uv run python -m backend.scripts.etl [TICKER]")

    TICKER = sys.argv[-1]

    hf  = get_financials(TICKER, 5)
    md  = get_market_data(TICKER)
    sd  = get_sector_data(date.today().year)
    a   = build_assumptions(hf)
    vi  = build_valuation_inputs(hf, md, sd)

    # ─────────────────────────────────────────────────────────────
    section(f"{TICKER} — Company")
    print(f"  {hf.metadata.name}  ({hf.metadata.industry})")
    print(f"  CIK: {hf.metadata.cik}  |  FY end: {hf.metadata.fiscal_year_end}")
    print(f"  {len(hf.periods)} fiscal periods loaded "
          f"({hf.periods[0].period_end} → {hf.periods[-1].period_end})")

    # ─────────────────────────────────────────────────────────────
    section("Sector Data")
    print(f"  {'ERP:':<22} {fmt_pct(sd.equity_risk_premium)}")
    print(f"  {'Terminal growth:':<22} {fmt_pct(sd.long_term_growth_rate)}")

    # ─────────────────────────────────────────────────────────────
    section("Market Data")
    print(f"  {'Risk-free rate:':<22} {fmt_pct(md.risk_free_rate)}")
    print(f"  {'Beta:':<22} {md.beta:>9.3f}")
    print(f"  {'Current Price:':<22} ${md.current_price:>8,.2f}")
    print(f"  {'Shares Outstanding:':<22} {md.shares_outstanding/1e9:>8,.2f}B")
    print(f"  {'Market Cap:':<22} {md.market_cap/1e9:>8,.2f}B")

    # ─────────────────────────────────────────────────────────────
    section("Assumptions (trailing averages)")
    print(f"  {'Revenue growth:':<22} {fmt_pct(a.revenue_growth)}")
    print(f"  {'EBIT margin:':<22} {fmt_pct(a.ebit_margin)}")
    print(f"  {'Tax rate:':<22} {fmt_pct(a.tax_rate)}")
    print(f"  {'D&A / revenue:':<22} {fmt_pct(a.depreciation_and_amortization_over_revenue)}")
    print(f"  {'CapEx / revenue:':<22} {fmt_pct(a.capex_over_revenue)}")
    print(f"  {'NWC / revenue:':<22} {fmt_pct(a.nwc_over_revenue)}")

    # ─────────────────────────────────────────────────────────────
    section("Valuation Inputs")
    print(f"  {'Beta:':<22} {vi.beta:>9.3f}")
    print(f"  {'Risk-free rate:':<22} {fmt_pct(vi.risk_free_rate)}")
    print(f"  {'ERP:':<22} {fmt_pct(vi.equity_risk_premium)}")
    print(f"  {'Cost of equity:':<22} {fmt_pct(vi.cost_of_capital)}")
    print(f"  {'Cost of debt:':<22} {fmt_pct(vi.cost_of_debt)}")
    print(f"  {'WACC:':<22} {fmt_pct(vi.wacc)}")
    print(f"  {'Terminal growth:':<22} {fmt_pct(vi.long_term_growth_rate)}")
    print(f"  {'Total debt:':<22} {vi.total_debt/1e9:>8,.2f}B")

    # ─────────────────────────────────────────────────────────────
    section("Working Capital")
    print(f"  {'Period':<12} {'NWC':>12} {'ΔNWC':>12}")
    for i, p in enumerate(hf.periods):
        nwc = p.balance_sheet.net_working_capital
        delta = (
            nwc - hf.periods[i-1].balance_sheet.net_working_capital
            if i > 0 and nwc is not None
            and hf.periods[i-1].balance_sheet.net_working_capital is not None
            else None
        )
        print(f"  {str(p.period_end):<12} {fmt_money(nwc)} {fmt_money(delta)}")

    # ─────────────────────────────────────────────────────────────
    section("Latest period — snapshot")
    latest = hf.periods[-1]
    print(f"  {'Period end:':<22} {latest.period_end}")
    print(f"  {'Revenue:':<22} {fmt_money(latest.income_statement.revenue)}")
    print(f"  {'EBIT:':<22} {fmt_money(latest.income_statement.ebit)}")
    print(f"  {'Net income:':<22} {fmt_money(latest.income_statement.net_income)}")
    print(f"  {'Total assets:':<22} {fmt_money(latest.balance_sheet.total_assets)}")
    print(f"  {'Total liabilities:':<22} {fmt_money(latest.balance_sheet.total_liabilities)}")
    print(f"  {'Total equity:':<22} {fmt_money(latest.balance_sheet.total_equity)}")
    print(f"  {'CFO:':<22} {fmt_money(latest.cash_flow.cfo)}")
    print(f"  {'CapEx:':<22} {fmt_money(latest.cash_flow.capex)}")
    print(f"  {'FCF:':<22} {fmt_money(latest.cash_flow.fcf)}")

    # ─────────────────────────────────────────────────────────────
    section("Historical revenue, EBIT, net income")
    print(f"  {'Period':<12} {'Revenue':>12} {'EBIT':>12} {'Net income':>12}")
    print(f"  {'-'*10:<12} {'-'*10:>12} {'-'*10:>12} {'-'*10:>12}")
    for p in hf.periods:
        print(
            f"  {str(p.period_end):<12} "
            f"{fmt_money(p.income_statement.revenue)} "
            f"{fmt_money(p.income_statement.ebit)} "
            f"{fmt_money(p.income_statement.net_income)}"
        )

    print()


# ─── Formatting helpers ──────────────────────────────────────────

def fmt_money(value: float | None, unit: str = "B") -> str:
    if value is None:
        return "     n/a"
    divisor = 1e9 if unit == "B" else 1e6
    return f"${value/divisor:>8,.2f}{unit}"

def fmt_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:>7.2%}"

def section(title: str) -> None:
    print(f"\n{'─' * 64}")
    print(f"  {title}")
    print(f"{'─' * 64}")


if __name__ == "__main__":
    main()