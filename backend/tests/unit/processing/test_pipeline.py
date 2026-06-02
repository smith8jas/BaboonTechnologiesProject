"""
Pytest suite for the HistoricalFinancials data intake pipeline.

Tests the full pipeline (fetch → preprocess → map → validate) for a
universe of tickers covering different industries and fiscal year ends.

JPM is explicitly excluded (unsupported: bank).
"""

import pytest
from edgar import Company, set_identity
from edgar.xbrl import XBRLS

from backend.core.config import settings
from backend.processing.xbrl_map import XBRL_MAPPINGS
from backend.processing.schema import (
    IncomeStatement,
    BalanceSheet,
    CashFlowStatement,
    HistoricalFinancials,
)


# ── Universe ──────────────────────────────────────────────────────────────────

SUPPORTED = [
    "AAPL",   # Apple — tech, Sep FY
    "WMT",    # Walmart — retail, Jan FY
    "XOM",    # ExxonMobil — energy, Dec FY
    "JNJ",    # Johnson & Johnson — pharma, Dec FY
    "BA",     # Boeing — aerospace, Dec FY (negative equity edge case)
    "TSLA",   # Tesla — auto/tech, Dec FY
    "T",      # AT&T — telecom, Dec FY (high debt)
    "KO",     # Coca-Cola — consumer staples, Dec FY
    "DIS",    # Disney — media, Sep FY
]

UNSUPPORTED = [
    "JPM",    # Bank — unsupported industry
]

HISTORICAL_SPAN = 3


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def set_edgar_identity():
    set_identity(settings.edgar_user_agent)


@pytest.fixture(scope="session")
def pipeline_results() -> dict[str, HistoricalFinancials]:
    """Run full pipeline for all supported tickers once per session."""
    results = {}
    for ticker in SUPPORTED:
        try:
            results[ticker] = run_pipeline(ticker)
        except Exception as e:
            results[ticker] = e
    return results


# ── Pipeline ──────────────────────────────────────────────────────────────────

def get_xbrls(ticker: str) -> XBRLS:
    filings = Company(ticker).get_filings(form="10-K", amendments=False)
    return XBRLS.from_filings(filings[:HISTORICAL_SPAN])


def preprocess(xbrls: XBRLS, statement: str) -> dict:
    statement_map = {
        "income_statement": "IncomeStatement",
        "balance_sheet":    "BalanceSheet",
        "cash_flow":        "CashFlowStatement",
    }
    df = (xbrls.facts.query()
        .to_dataframe()
        .pipe(lambda d: d[d["statement_type"] == statement_map[statement]])
        .pipe(lambda d: d[d["standard_concept"].notna()])
        .pipe(lambda d: d[~d["is_abstract"]])
        .sort_values("is_total", ascending=False)
        .drop_duplicates(subset=["standard_concept", "period_end"], keep="first")
    )
    return (
        df.groupby("standard_concept")
        .apply(lambda x: dict(zip(x["period_end"], x["numeric_value"])))
        .to_dict()
    )


def to_period_first(data: dict) -> dict:
    out = {}
    for concept, periods in data.items():
        for period, value in periods.items():
            out.setdefault(period, {})[concept] = value
    return out


def map_all_periods(by_period: dict, mappings: dict) -> dict:
    reverse = {v: k for k, v in mappings.items()}
    return {
        period: {reverse[k]: v for k, v in row.items() if k in reverse}
        for period, row in by_period.items()
    }


def run_pipeline(ticker: str) -> HistoricalFinancials:
    xbrls = get_xbrls(ticker)

    mapped_is = map_all_periods(to_period_first(preprocess(xbrls, "income_statement")), XBRL_MAPPINGS)
    mapped_bs = map_all_periods(to_period_first(preprocess(xbrls, "balance_sheet")),    XBRL_MAPPINGS)
    mapped_cf = map_all_periods(to_period_first(preprocess(xbrls, "cash_flow")),        XBRL_MAPPINGS)

    return HistoricalFinancials(
        ticker=ticker,
        income_statements={p: IncomeStatement(**mapped_is[p]) for p in mapped_is},
        balance_sheets={p: BalanceSheet(**mapped_bs[p]) for p in mapped_bs},
        cash_flows={p: CashFlowStatement(**mapped_cf[p]) for p in mapped_cf},
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ticker", SUPPORTED)
class TestPipeline:

    def test_pipeline_runs(self, ticker, pipeline_results):
        """Pipeline completes without exceptions."""
        result = pipeline_results[ticker]
        assert not isinstance(result, Exception), (
            f"{ticker} pipeline failed: {result}"
        )

    def test_has_three_periods(self, ticker, pipeline_results):
        """All three statements have exactly 3 periods."""
        hf: HistoricalFinancials = pipeline_results[ticker]
        assert len(hf.income_statements) == HISTORICAL_SPAN, \
            f"{ticker}: expected {HISTORICAL_SPAN} IS periods, got {len(hf.income_statements)}"
        assert len(hf.balance_sheets) == HISTORICAL_SPAN, \
            f"{ticker}: expected {HISTORICAL_SPAN} BS periods, got {len(hf.balance_sheets)}"
        assert len(hf.cash_flows) == HISTORICAL_SPAN, \
            f"{ticker}: expected {HISTORICAL_SPAN} CF periods, got {len(hf.cash_flows)}"

    def test_revenue_positive(self, ticker, pipeline_results):
        """Revenue is positive for all periods."""
        hf: HistoricalFinancials = pipeline_results[ticker]
        for period, stmt in hf.income_statements.items():
            assert stmt.revenue is not None, f"{ticker} [{period}]: revenue is None"
            assert stmt.revenue > 0, f"{ticker} [{period}]: revenue={stmt.revenue} not positive"

    def test_net_income_present(self, ticker, pipeline_results):
        """Net income is present for all periods."""
        hf: HistoricalFinancials = pipeline_results[ticker]
        for period, stmt in hf.income_statements.items():
            assert stmt.net_income is not None, \
                f"{ticker} [{period}]: net_income is None"

    def test_operating_income_present(self, ticker, pipeline_results):
        """Operating income (EBIT) is present for all periods."""
        hf: HistoricalFinancials = pipeline_results[ticker]
        for period, stmt in hf.income_statements.items():
            assert stmt.operating_income is not None, \
                f"{ticker} [{period}]: operating_income is None"

    def test_gross_profit_consistent(self, ticker, pipeline_results):
        """Gross profit ≈ revenue - cogs within 1%."""
        hf: HistoricalFinancials = pipeline_results[ticker]
        for period, stmt in hf.income_statements.items():
            if stmt.revenue and stmt.cogs and stmt.gross_profit:
                diff = abs((stmt.revenue - stmt.cogs) - stmt.gross_profit)
                assert diff <= stmt.revenue * 0.01, \
                    f"{ticker} [{period}]: gross profit mismatch diff={diff:,.0f}"

    def test_balance_sheet_identity(self, ticker, pipeline_results):
        """Assets ≈ liabilities + equity within 5%."""
        hf: HistoricalFinancials = pipeline_results[ticker]
        for period, bs in hf.balance_sheets.items():
            if bs.total_assets and bs.total_liabilities and bs.total_equity:
                diff = abs(bs.total_assets - (bs.total_liabilities + bs.total_equity))
                assert diff <= bs.total_assets * 0.05, \
                    f"{ticker} [{period}]: BS gap={diff:,.0f} ({diff/bs.total_assets:.1%})"

    def test_total_assets_positive(self, ticker, pipeline_results):
        """Total assets are positive."""
        hf: HistoricalFinancials = pipeline_results[ticker]
        for period, bs in hf.balance_sheets.items():
            assert bs.total_assets is not None, f"{ticker} [{period}]: total_assets is None"
            assert bs.total_assets > 0, f"{ticker} [{period}]: total_assets not positive"

    def test_capex_present(self, ticker, pipeline_results):
        """CapEx is present for all periods."""
        hf: HistoricalFinancials = pipeline_results[ticker]
        for period, cf in hf.cash_flows.items():
            assert cf.capex is not None, f"{ticker} [{period}]: capex is None"

    def test_cfo_present(self, ticker, pipeline_results):
        """Operating cash flow is present for all periods."""
        hf: HistoricalFinancials = pipeline_results[ticker]
        for period, cf in hf.cash_flows.items():
            assert cf.cfo is not None, f"{ticker} [{period}]: cfo is None"

    def test_net_income_cf_matches_is(self, ticker, pipeline_results):
        """Net income in CF reconciles with IS within 1%."""
        hf: HistoricalFinancials = pipeline_results[ticker]
        for period in hf.income_statements:
            if period not in hf.cash_flows:
                continue
            is_ni = hf.income_statements[period].net_income
            cf_ni = hf.cash_flows[period].net_income
            if is_ni and cf_ni:
                diff = abs(is_ni - cf_ni)
                assert diff <= abs(is_ni) * 0.01, \
                    f"{ticker} [{period}]: NI mismatch IS={is_ni:,.0f} CF={cf_ni:,.0f}"

    def test_periods_aligned(self, ticker, pipeline_results):
        """All three statements cover the same periods."""
        hf: HistoricalFinancials = pipeline_results[ticker]
        is_periods = set(hf.income_statements.keys())
        bs_periods = set(hf.balance_sheets.keys())
        cf_periods = set(hf.cash_flows.keys())
        assert is_periods == bs_periods == cf_periods, \
            f"{ticker}: period mismatch IS={is_periods} BS={bs_periods} CF={cf_periods}"


# ── Unsupported tickers ───────────────────────────────────────────────────────

@pytest.mark.parametrize("ticker", UNSUPPORTED)
def test_unsupported_ticker_raises(ticker):
    """Unsupported industries should raise before pipeline runs."""
    with pytest.raises((ValueError, NotImplementedError)):
        run_pipeline(ticker)