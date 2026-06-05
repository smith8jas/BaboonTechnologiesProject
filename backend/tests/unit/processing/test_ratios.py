"""Unit tests for liquidity and solvency ratio calculations."""

from datetime import date

from backend.services.ratio import (
    current_ratio,
    quick_ratio,
    debt_to_equity,
    interest_coverage,
    get_efficiency_ratios,
)
from backend.processing.schema import (
    BalanceSheet,
    CashFlowStatement,
    CompanyMetadata,
    FinancialPeriod,
    HistoricalFinancials,
    IncomeStatement,
    PerShare,
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


class TestEfficiencyRatios:
    def test_uses_cogs_field_from_income_statement(self):
        financials = HistoricalFinancials(
            ticker="TEST",
            metadata=CompanyMetadata(
                cik="0000000000",
                name="Test Company",
                fiscal_year_end="1231",
            ),
            periods=[
                FinancialPeriod(
                    period_end=date(2025, 12, 31),
                    income_statement=IncomeStatement(
                        revenue=1000.0,
                        cogs=400.0,
                    ),
                    balance_sheet=BalanceSheet(
                        accounts_receivable=100.0,
                        inventory=80.0,
                        accounts_payable=40.0,
                    ),
                    cash_flow=CashFlowStatement(),
                    per_share=PerShare(),
                )
            ],
        )

        assert get_efficiency_ratios(financials) == {
            "FY2025": {
                "dso": 36.5,
                "dio": 73.0,
                "dpo": 36.5,
            }
        }
