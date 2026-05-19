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
    print(f"  Net income:               {fmt_money(latest.income_statement.net_income)}")
    print(f"  Total assets:             {fmt_money(latest.balance_sheet.total_assets)}")
    print(f"  Total liabilities:        {fmt_money(latest.balance_sheet.total_liabilities)}")
    print(f"  Total equity:             {fmt_money(latest.balance_sheet.total_equity)}")
    print(f"  Balances =                {fmt_money(latest.balance_sheet.total_assets - (latest.balance_sheet.total_liabilities + latest.balance_sheet.total_equity))}")
    print(f"  CFO:                      {fmt_money(latest.cash_flow.cfo)}")
    print(f"  CapEx:                    {fmt_money(latest.cash_flow.capex)}")
    print(f"  FCF:                      {fmt_money(latest.cash_flow.fcf)}")
    print(f"  Basic Shares:             {latest.per_share.basic_shares/1e9:>8,.2f}B")
    print(f"  Diluted Shares:           {latest.per_share.diluted_shares/1e9:>8,.2f}B")

    # ─────────────────────────────────────────────────────────────
    section("Historical revenue, EBIT, net income")