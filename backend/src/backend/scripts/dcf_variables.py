"""CLI harness: fetch and display financials + market data for a ticker."""

import sys

from backend.services.financials import get_financials, get_market_data


def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: uv run python -m backend.scripts.etl [TICKER]")

    TICKER = sys.argv[-1]
    SPAN = 5

    hf = get_financials(TICKER, SPAN)
    md = get_market_data(TICKER)

    # ─────────────────────────────────────────────────────────────
    section(f"{TICKER} — Company")
    print(f"  {hf.metadata.name}  ({hf.metadata.industry})")
    print(f"  CIK: {hf.metadata.cik}  |  FY end: {hf.metadata.fiscal_year_end}")
    print(f"  {len(hf.periods)} fiscal periods loaded "
          f"({hf.periods[0].period_end} → {hf.periods[-1].period_end})")

    # ─────────────────────────────────────────────────────────────
    section("Latest period — snapshot")
    latest = hf.periods[-1]
    print(f"  Period end:               {latest.period_end}")
    print(f"  Revenue:                  {fmt_money(latest.income_statement.revenue)}")
    print(f"  EBIT:                     {fmt_money(latest.income_statement.ebit)}")
    print(f"  Depreciation:             {fmt_money(latest.income_statement.depreciation_expense)}")
    print(f"  CapEx:                    {fmt_money(latest.cash_flow.capex)}")
    print(f"  Net Working Capital:      {fmt_money(latest.balance_sheet.net_working_capital)}")
    print(f"  Tax Expense:              {fmt_money(latest.income_statement.tax_expense)}")
    print(f"  EBIAT:                    {fmt_money(latest.income_statement.ebiat)}")

    # ─────────────────────────────────────────────────────────────
    section("Find by year — FY2024")
    y2024 = next((p for p in hf.periods if p.period_end.year == 2024), None)
    if y2024:
        print(f"  Period end:     {y2024.period_end}")
        print(f"  Revenue:        {fmt_money(y2024.income_statement.revenue)}")
        print(f"  Total assets:   {fmt_money(y2024.balance_sheet.total_assets)}")
    else:
        print("  No FY2024 period in history.")

    # ─────────────────────────────────────────────────────────────
    section(f"{TICKER} — Market Data")
    print(f"  Current price:    ${md.current_price:>8,.2f}")
    print(f"  Beta:             {md.beta:>9,.3f}")
    print(f"  Shares out:       {md.shares_outstanding/1e9:>8,.2f}B")
    print(f"  Market cap:       {fmt_money(md.market_cap, 'B')}")
    print(f"  Risk-free rate:   {fmt_pct(md.risk_free_rate)}")

    print()


# ─── Formatting helpers ──────────────────────────────────────────

def fmt_money(value: float | None, unit: str = "B") -> str:
    if value is None:
        return "n/a"
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