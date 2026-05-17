import sys
import json
from datetime import date

from backend.adapters.edgar import Edgar
from backend.adapters.yahoo_finance import fetch_yahoo_market
from backend.adapters.fred import fetch_risk_free_rate
from backend.processing.xbrl_map import (
    PS_MAPPINGS, 
    IS_MAPPINGS, 
    BS_MAPPINGS, 
    CFS_MAPPINGS,
    map_keys,
    map_all_periods,
)
from backend.processing.schema import(
    MarketData,             # Yahoo Finance
    # NewsData,             # Raw and vector embeddings of news 
    # EconomicData,         # Damodaran, FRED
    PerShare,               # Edgar - Shares outstanding
    IncomeStatement,        # Edgar
    BalanceSheet,           # ''
    CashFlowStatement,      # ''
    CompanyMetadata,        # ''
    FinancialPeriod,
    HistoricalFinancials,   # All aggregated
)



def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: uv run [program_name] [TICKER]")
    
    # Variables
    TICKER = sys.argv[-1]
    SPAN = 5

    # 1. Extract -----------------------------------------------------------

    # Raw edgar data
    company = Edgar(TICKER)
    raw_metadata = company.metadata()
    financials = company.fetch_all(SPAN) 

    # Raw yfinance data
    yahoo = fetch_yahoo_market(TICKER)   # price, beta, shares, market_cap
    rfr   = fetch_risk_free_rate()       # FRED DGS10

    # 2. Transform ---------------------------------------------------------

    # Mappings
    mapped_ps = map_all_periods(financials["income_statement"], PS_MAPPINGS)
    mapped_is = map_all_periods(financials["income_statement"], IS_MAPPINGS)
    mapped_bs = map_all_periods(financials["balance_sheet"], BS_MAPPINGS)
    mapped_cf = map_all_periods(financials["cash_flow"], CFS_MAPPINGS)

    # Union of all period keys, sorted oldest → newest
    all_period_keys = sorted(
        set(mapped_is) | set(mapped_bs) | set(mapped_cf) | set(mapped_ps)
    )

    periods = [
        FinancialPeriod(
            period_end=date.fromisoformat(p),
            income_statement=IncomeStatement(**mapped_is.get(p, {})),
            balance_sheet=BalanceSheet(**mapped_bs.get(p, {})),
            cash_flow=CashFlowStatement(**mapped_cf.get(p, {})),
            per_share=PerShare(**mapped_ps.get(p, {})),
        )
        for p in all_period_keys
    ]

    metadata = CompanyMetadata(**raw_metadata)

    hf = HistoricalFinancials(
        ticker=TICKER,
        metadata=metadata,
        periods=periods,
    )

    md = MarketData(
        current_price=yahoo["current_price"],
        beta=yahoo["beta"],
        shares_outstanding=yahoo["shares_outstanding"],
        market_cap=yahoo["market_cap"],
        risk_free_rate=rfr,
    )

    # 3. Load

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
    header = f"  {'Period':<12} {'Revenue':>12} {'EBIT':>12} {'Net income':>12}"
    print(header)
    print(f"  {'-'*10:<12} {'-'*10:>12} {'-'*10:>12} {'-'*10:>12}")
    for p in hf.periods:
        print(
            f"  {str(p.period_end):<12} "
            f"{fmt_money(p.income_statement.revenue)} "
            f"{fmt_money(p.income_statement.ebit)} "
            f"{fmt_money(p.income_statement.net_income)}"
        )

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

    print()  # trailing newline


# Helper formatting functions -- IGNORE

def fmt_money(value: float | None, unit: str = "B") -> str:
    """Format large numbers as $X.XB or $X.XM."""
    if value is None:
        return "n/a"
    divisor = 1e9 if unit == "B" else 1e6
    return f"${value/divisor:>8,.2f}{unit}"

def fmt_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:>7.2%}"

def fmt_num(value: float | None) -> str:
    return "n/a" if value is None else f"{value:>12,.2f}"


def section(title: str) -> None:
    """Print a labeled section header."""
    print(f"\n{'─' * 64}")
    print(f"  {title}")
    print(f"{'─' * 64}")


if __name__ == "__main__":
    main()
