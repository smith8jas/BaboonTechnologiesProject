"""Unit tests for liquidity and solvency ratio calculations."""

import math
import pytest

from backend.services.ratio import (
    current_ratio,
    quick_ratio,
    debt_to_equity,
    interest_coverage,
)


# ---------- current_ratio ----------

class TestCurrentRatio:
    def test_basic(self):
        assert current_ratio([200.0, 300.0], [100.0, 150.0]) == [2.0, 2.0]

    def test_below_one(self):
        result = current_ratio([50.0], [100.0])
        assert result == [0.5]

    def test_zero_liabilities_returns_zero(self):
        assert current_ratio([100.0], [0]) == [0]

    def test_none_liabilities_returns_zero(self):
        assert current_ratio([100.0], [None]) == [0]

    def test_empty_inputs(self):
        assert current_ratio([], []) == []

    def test_mixed_valid_and_zero(self):
        result = current_ratio([200.0, 100.0], [100.0, 0])
        assert result == [2.0, 0]


# ---------- quick_ratio ----------

class TestQuickRatio:
    def test_basic(self):
        # (200 - 50) / 100 = 1.5
        assert quick_ratio([200.0], [50.0], [100.0]) == [1.5]

    def test_zero_inventory_equals_current_ratio(self):
        assert quick_ratio([200.0], [0.0], [100.0]) == current_ratio([200.0], [100.0])

    def test_inventory_exceeds_assets_negative(self):
        # (100 - 150) / 50 = -1.0 — function does not guard against negatives
        assert quick_ratio([100.0], [150.0], [50.0]) == [-1.0]

    def test_zero_liabilities_returns_zero(self):
        assert quick_ratio([200.0], [50.0], [0]) == [0]

    def test_none_liabilities_returns_zero(self):
        assert quick_ratio([200.0], [50.0], [None]) == [0]

    def test_multi_period(self):
        result = quick_ratio([200.0, 300.0], [50.0, 100.0], [100.0, 100.0])
        assert result == [1.5, 2.0]


# ---------- debt_to_equity ----------

class TestDebtToEquity:
    def test_basic(self):
        assert debt_to_equity([500.0], [250.0]) == [2.0]

    def test_zero_debt(self):
        assert debt_to_equity([0.0], [100.0]) == [0.0]

    def test_zero_equity_returns_zero(self):
        assert debt_to_equity([500.0], [0]) == [0]

    def test_none_equity_returns_zero(self):
        assert debt_to_equity([500.0], [None]) == [0]

    def test_negative_equity_allowed(self):
        # Real-world case: insolvent company. Function returns raw ratio.
        assert debt_to_equity([500.0], [-100.0]) == [-5.0]


# ---------- interest_coverage ----------

class TestInterestCoverage:
    def test_basic(self):
        assert interest_coverage([1000.0], [100.0]) == [10.0]

    def test_zero_interest_returns_zero(self):
        # Note: arithmetically should be infinite; function returns 0 by design
        assert interest_coverage([1000.0], [0]) == [0]

    def test_none_interest_returns_zero(self):
        assert interest_coverage([1000.0], [None]) == [0]

    def test_negative_ebit(self):
        # Operating loss — company cannot cover interest
        assert interest_coverage([-500.0], [100.0]) == [-5.0]

    def test_multi_period(self):
        assert interest_coverage([1000.0, 500.0], [100.0, 250.0]) == [10.0, 2.0]


# ---------- shared behavior ----------

class TestZipTruncation:
    """zip() silently truncates to shortest input — documents current behavior."""

    def test_current_ratio_mismatched_lengths(self):
        assert current_ratio([100.0, 200.0, 300.0], [50.0]) == [2.0]

    def test_debt_to_equity_mismatched_lengths(self):
        assert debt_to_equity([100.0], [50.0, 25.0]) == [2.0]
