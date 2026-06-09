import sys

def test_erp():
    erp = fetch_equity_risk_premium()
    assert erp is not None, "ERP returned None"
    assert 0.01 < erp < 0.20, f"ERP out of plausible range: {erp}"
    print(f"  ERP: {erp:.4f}")

def test_trailing_pe():
    for industry in ["Total Market", "Software (System & Application)", "Semiconductor"]:
        val = fetch_trailing_pe(industry)
        assert val is not None, f"Trailing PE None for '{industry}'"
        assert val > 0, f"Trailing PE non-positive for '{industry}': {val}"
        print(f"  Trailing PE [{industry}]: {val:.2f}")

def test_ev_sales():
    for industry in ["Total Market", "Software (System & Application)", "Retail (Grocery and Food)"]:
        val = fetch_ev_sales(industry)
        assert val is not None, f"EV/Sales None for '{industry}'"
        assert val > 0, f"EV/Sales non-positive for '{industry}': {val}"
        print(f"  EV/Sales [{industry}]: {val:.2f}")

def test_price_sales():
    for industry in ["Total Market", "Semiconductor", "Air Transport"]:
        val = fetch_price_sales(industry)
        assert val is not None, f"P/S None for '{industry}'"
        assert val > 0, f"P/S non-positive for '{industry}': {val}"
        print(f"  P/S [{industry}]: {val:.2f}")

def test_unknown_industry():
    val = fetch_trailing_pe("Nonexistent Industry XYZ")
    assert val is None, f"Expected None for unknown industry, got {val}"
    print("  Unknown industry correctly returns None")

if __name__ == "__main__":
    from backend.adapters.damodaran import (
        fetch_equity_risk_premium,
        fetch_trailing_pe,
        fetch_ev_sales,
        fetch_price_sales,
    )

    tests = [
        test_erp,
        test_trailing_pe,
        test_ev_sales,
        test_price_sales,
        test_unknown_industry,
    ]

    failed = 0
    for t in tests:
        try:
            print(f"[{t.__name__}]")
            t()
            print(f"  PASS\n")
        except Exception as e:
            print(f"  FAIL: {e}\n")
            failed += 1

    sys.exit(failed)