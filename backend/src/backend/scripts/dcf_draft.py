"""CLI harness: fetch and display financials + market data for a ticker."""

import sys

from backend.services.financials import get_financials, get_market_data
import numpy as np


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
    section("DCF Engine")
    print(f"  {hf.model_dump_json(indent=2)}")


# ─── DCF functions ──────────────────────────────────────────

def interpolate(initial_value, terminal_value, nyears):
    return np.linspace(initial_value, terminal_value, nyears)


def pct_change(financials):
    ...


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