"""Lean DCF — illustrates the agent's job: four calls, one result."""

import sys
from datetime import date

from backend.services.financials import get_financials, get_market_data, get_sector_data
from backend.services.dcf_engine import build_valuation_inputs, run_dcf
from backend.services.forecast import build_forecast_assumptions


def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: uv run python -m backend.scripts.dcf_lean [TICKER]")

    TICKER = sys.argv[-1]

    hf     = get_financials(TICKER, 5)
    md     = get_market_data(TICKER)
    sd     = get_sector_data(date.today().year)
    fa     = build_forecast_assumptions(hf, md, sd)
    a      = fa.to_assumptions()
    vi     = build_valuation_inputs(hf, md, sd, a)
    result = run_dcf(hf, vi, a, forecast=fa)

    print(f"{TICKER}  intrinsic value/share: ${result.intrinsic_value_per_share:,.2f}")


if __name__ == "__main__":
    main()