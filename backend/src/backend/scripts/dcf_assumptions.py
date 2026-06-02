"""Test build_assumptions against known AAPL trailing averages."""

from backend.services.financials import get_financials
from backend.services.dcf_engine import build_assumptions

TOLERANCE = 0.001  # 0.1%

def test_build_assumptions():
    hf = get_financials("AAPL", 5)
    a = build_assumptions(hf)

    assert abs(a.revenue_growth - 0.0336) < TOLERANCE, f"revenue_growth: {a.revenue_growth:.4f}"
    assert abs(a.ebit_margin    - 0.3067) < TOLERANCE, f"ebit_margin:    {a.ebit_margin:.4f}"
    assert abs(a.tax_rate       - 0.1677) < TOLERANCE, f"tax_rate:       {a.tax_rate:.4f}"
    assert abs(a.depreciation_and_amortization_over_revenue - 0.0293) < TOLERANCE, f"da_pct: {a.depreciation_and_amortization_over_revenue:.4f}"
    assert abs(a.capex_over_revenue  - 0.0282) < TOLERANCE, f"capex_pct: {a.capex_over_revenue:.4f}"
    assert abs(a.nwc_over_revenue    - (-0.0257)) < TOLERANCE, f"nwc_pct: {a.nwc_over_revenue:.4f}"

    print("✓ All assumptions match Excel reference")
    print(f"  revenue_growth  {a.revenue_growth:.4f}")
    print(f"  ebit_margin     {a.ebit_margin:.4f}")
    print(f"  tax_rate        {a.tax_rate:.4f}")
    print(f"  da_pct          {a.depreciation_and_amortization_over_revenue:.4f}")
    print(f"  capex_pct       {a.capex_over_revenue:.4f}")
    print(f"  nwc_pct         {a.nwc_over_revenue:.4f}")


if __name__ == "__main__":
    test_build_assumptions()