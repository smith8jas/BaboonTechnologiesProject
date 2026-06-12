"""Tests for the agent data-cache layer and for how cache state evolves.

Part 1 — cache classes: each get_or_fetch / get_or_calculate hits the external
service exactly once and serves repeats from the cache dict.

Part 2 — tool layer: tools write through the injected data_cache and report
"cache" vs "external" sources.

Part 3 — state evolution: the data_cache merges across sequential and parallel
node updates the way the LangGraph merge_cache reducer applies them, and the
catalog/payload views grow accordingly.
"""

from copy import deepcopy
from unittest.mock import MagicMock, patch

from backend.agent.cache import (
    CompsCache,
    DCFCache,
    FinancialsCache,
    GrowthCache,
    MarketDataCache,
    RatiosCache,
    SectorDataCache,
    build_data_catalog,
    build_data_payload,
    empty_data_cache,
    empty_data_catalog,
    state_cache,
    tool_content,
)
from backend.agent.cache.schema import SUBDOMAIN_INCOME_STATEMENT
from backend.agent.state import merge_cache
from backend.processing.schema import HistoricalFinancials, MarketData, SectorData


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _mock_hf(ticker: str, fiscal_years: list[int]) -> HistoricalFinancials:
    return HistoricalFinancials.model_validate(
        {
            "ticker": ticker,
            "metadata": {"cik": f"{ticker}-CIK", "name": ticker},
            "periods": [
                {
                    "fiscal_year": str(y),
                    "period_end": f"{y}-12-31",
                    "income_statement": {},
                    "balance_sheet": {},
                    "cash_flow": {},
                    "per_share": {},
                }
                for y in fiscal_years
            ],
        }
    )


def _mock_md() -> MarketData:
    return MarketData(
        current_price=100.0,
        beta=1.1,
        shares_outstanding=1e9,
        market_cap=1e11,
        risk_free_rate=0.04,
    )


def _mock_sd() -> SectorData:
    return SectorData(equity_risk_premium=0.05, long_term_growth_rate=0.025)


def _cache_with_financials(ticker: str, fiscal_years: list[int]) -> dict:
    cache = empty_data_cache()
    FinancialsCache._store(cache, _mock_hf(ticker, fiscal_years), span=len(fiscal_years))
    return cache


# ---------------------------------------------------------------------------
# Part 1 — cache classes fetch once, then reuse
# ---------------------------------------------------------------------------

def test_financials_fetch_then_hit():
    cache = empty_data_cache()
    with patch("backend.agent.cache.financials.financials_service") as mock_fin:
        mock_fin.get_cached_financials.return_value = _mock_hf("AAPL", [2022, 2023, 2024])

        _, first_cached = FinancialsCache.get_or_fetch(cache, "AAPL", span=3)
        _, second_cached = FinancialsCache.get_or_fetch(cache, "AAPL", span=3)

        assert mock_fin.get_cached_financials.call_count == 1
    assert (first_cached, second_cached) == (False, True)


def test_financials_wider_span_refetches():
    cache = _cache_with_financials("AAPL", [2023, 2024])
    with patch("backend.agent.cache.financials.financials_service") as mock_fin:
        mock_fin.get_cached_financials.return_value = _mock_hf("AAPL", [2020, 2021, 2022, 2023, 2024])
        _, was_cached = FinancialsCache.get_or_fetch(cache, "AAPL", span=5)
        mock_fin.get_cached_financials.assert_called_once_with("AAPL", 5)
    assert was_cached is False


def test_market_data_fetch_then_hit():
    cache = empty_data_cache()
    with patch("backend.agent.cache.market_data.financials_service") as mock_fin:
        mock_fin.get_market_data.return_value = _mock_md()

        _, first_cached = MarketDataCache.get_or_fetch(cache, "AAPL", include_rfr=True)
        _, second_cached = MarketDataCache.get_or_fetch(cache, "AAPL", include_rfr=True)

        assert mock_fin.get_market_data.call_count == 1
    assert (first_cached, second_cached) == (False, True)


def test_market_data_without_rfr_does_not_satisfy_rfr_request():
    cache = empty_data_cache()
    with patch("backend.agent.cache.market_data.financials_service") as mock_fin:
        mock_fin.get_market_data.return_value = _mock_md()

        MarketDataCache.get_or_fetch(cache, "AAPL", include_rfr=False)
        _, was_cached = MarketDataCache.get_or_fetch(cache, "AAPL", include_rfr=True)

        assert mock_fin.get_market_data.call_count == 2
    assert was_cached is False


def test_market_data_with_rfr_satisfies_no_rfr_request():
    cache = empty_data_cache()
    with patch("backend.agent.cache.market_data.financials_service") as mock_fin:
        mock_fin.get_market_data.return_value = _mock_md()

        MarketDataCache.get_or_fetch(cache, "AAPL", include_rfr=True)
        _, was_cached = MarketDataCache.get_or_fetch(cache, "AAPL", include_rfr=False)

        assert mock_fin.get_market_data.call_count == 1
    assert was_cached is True


def test_sector_data_cached_per_year():
    cache = empty_data_cache()
    with patch("backend.agent.cache.sector_data.financials_service") as mock_fin:
        mock_fin.get_sector_data.return_value = _mock_sd()

        _, first_cached = SectorDataCache.get_or_fetch(cache, 2024)
        _, second_cached = SectorDataCache.get_or_fetch(cache, 2024)
        _, other_year_cached = SectorDataCache.get_or_fetch(cache, 2023)

        assert mock_fin.get_sector_data.call_count == 2
    assert (first_cached, second_cached, other_year_cached) == (False, True, False)


def test_growth_calculates_from_cached_financials_without_external_call():
    cache = _cache_with_financials("AAPL", [2020, 2021, 2022, 2023, 2024])
    with (
        patch("backend.agent.cache.financials.financials_service") as mock_fin,
        patch("backend.agent.cache.growth.growth_service") as mock_growth,
    ):
        mock_growth.get_income_statement_growth_rates.return_value = {"revenue": [0.1]}

        _, first_cached = GrowthCache.get_or_calculate(cache, "AAPL", 5, SUBDOMAIN_INCOME_STATEMENT)
        _, second_cached = GrowthCache.get_or_calculate(cache, "AAPL", 5, SUBDOMAIN_INCOME_STATEMENT)

        mock_fin.get_cached_financials.assert_not_called()
        assert mock_growth.get_income_statement_growth_rates.call_count == 1
    assert (first_cached, second_cached) == (False, True)


def test_ratios_calculate_once_then_reuse():
    cache = _cache_with_financials("AAPL", [2020, 2021, 2022, 2023, 2024])
    fake_liquidity = MagicMock(return_value={"current_ratio": [1.5]})
    with patch.dict(RatiosCache._RATIO_FUNCS, {"liquidity": fake_liquidity}):
        _, first_cached = RatiosCache.get_or_calculate(cache, "AAPL", 5, "liquidity")
        _, second_cached = RatiosCache.get_or_calculate(cache, "AAPL", 5, "liquidity")

        assert fake_liquidity.call_count == 1
    assert (first_cached, second_cached) == (False, True)


def test_ratios_narrower_span_is_satisfied_by_wider_coverage():
    cache = _cache_with_financials("AAPL", [2020, 2021, 2022, 2023, 2024])
    fake_liquidity = MagicMock(return_value={"current_ratio": [1.5]})
    with patch.dict(RatiosCache._RATIO_FUNCS, {"liquidity": fake_liquidity}):
        RatiosCache.get_or_calculate(cache, "AAPL", 5, "liquidity")
        _, was_cached = RatiosCache.get_or_calculate(cache, "AAPL", 3, "liquidity")
    assert was_cached is True


def test_dcf_calculates_once_then_reuses_for_same_span_and_year():
    cache = _cache_with_financials("AAPL", [2020, 2021, 2022, 2023, 2024])
    dcf_result = MagicMock(fiscal_year="FY2024", projection_years=["FY2025"])
    dcf_result.model_dump.return_value = {
        "fiscal_year": "FY2024",
        "projection_years": ["FY2025"],
        "intrinsic_value_per_share": 123.0,
    }
    with (
        patch("backend.agent.cache.market_data.financials_service") as mock_fin,
        patch("backend.agent.cache.sector_data.financials_service") as mock_sector,
        patch("backend.agent.cache.dcf.dcf_engine") as mock_engine,
    ):
        mock_fin.get_market_data.return_value = _mock_md()
        mock_sector.get_sector_data.return_value = _mock_sd()
        mock_engine.run_dcf.return_value = dcf_result

        payload, first_cached = DCFCache.get_or_calculate(cache, "AAPL", 5, 2024)
        _, second_cached = DCFCache.get_or_calculate(cache, "AAPL", 5, 2024)

        assert mock_engine.run_dcf.call_count == 1
    assert (first_cached, second_cached) == (False, True)
    assert payload["intrinsic_value_per_share"] == 123.0


def test_dcf_different_sector_year_recalculates():
    cache = _cache_with_financials("AAPL", [2020, 2021, 2022, 2023, 2024])
    dcf_result = MagicMock(fiscal_year="FY2024", projection_years=["FY2025"])
    dcf_result.model_dump.return_value = {"fiscal_year": "FY2024", "projection_years": ["FY2025"]}
    with (
        patch("backend.agent.cache.market_data.financials_service") as mock_fin,
        patch("backend.agent.cache.sector_data.financials_service") as mock_sector,
        patch("backend.agent.cache.dcf.dcf_engine") as mock_engine,
    ):
        mock_fin.get_market_data.return_value = _mock_md()
        mock_sector.get_sector_data.return_value = _mock_sd()
        mock_engine.run_dcf.return_value = dcf_result

        DCFCache.get_or_calculate(cache, "AAPL", 5, 2024)
        _, was_cached = DCFCache.get_or_calculate(cache, "AAPL", 5, 2023)

        assert mock_engine.run_dcf.call_count == 2
    assert was_cached is False


def test_comps_peer_reuses_for_same_peer_set_recomputes_for_new():
    cache = empty_data_cache()
    with patch("backend.agent.cache.comparables.comparables_service") as mock_comps:
        mock_comps.peer_comps.return_value = {"source": "peer comparables"}

        _, first_cached = CompsCache.get_or_calculate_peer(cache, "AAPL", ["MSFT", "GOOGL"])
        _, reordered_cached = CompsCache.get_or_calculate_peer(cache, "AAPL", ["googl", "msft"])
        _, new_peers_cached = CompsCache.get_or_calculate_peer(cache, "AAPL", ["MSFT"])

        assert mock_comps.peer_comps.call_count == 2
    assert (first_cached, reordered_cached, new_peers_cached) == (False, True, False)


def test_comps_damodaran_cached_after_first_call():
    cache = empty_data_cache()
    with patch("backend.agent.cache.comparables.comparables_service") as mock_comps:
        mock_comps.damodaran_fallback.return_value = {"source": "damodaran"}

        _, first_cached = CompsCache.get_or_calculate_damodaran(cache, "AAPL")
        _, second_cached = CompsCache.get_or_calculate_damodaran(cache, "AAPL")

        assert mock_comps.damodaran_fallback.call_count == 1
    assert (first_cached, second_cached) == (False, True)


# ---------------------------------------------------------------------------
# Part 2 — tool layer writes through the injected data_cache
# ---------------------------------------------------------------------------

def test_get_financials_tool_reports_external_then_cache():
    from backend.agent.tools.research import get_financials

    cache = empty_data_cache()
    with patch("backend.agent.cache.financials.financials_service") as mock_fin:
        mock_fin.get_cached_financials.return_value = _mock_hf("AAPL", [2022, 2023, 2024])

        first = get_financials.invoke({"ticker": "AAPL", "span": 3, "data_cache": cache})
        second = get_financials.invoke({"ticker": "AAPL", "span": 3, "data_cache": cache})

    assert first["source"] == "external"
    assert second["source"] == "cache"
    assert "AAPL" in cache["companies"]


def test_tool_content_serializes_models_and_dicts():
    assert '"source"' in tool_content({"source": "cache"})
    assert '"current_price"' in tool_content(_mock_md())


# ---------------------------------------------------------------------------
# Part 3 — state evolution across updates
# ---------------------------------------------------------------------------

def test_state_cache_normalizes_missing_keys():
    cache = state_cache({})
    assert cache["companies"] == {}
    assert cache["global"]["sector_data_by_year"] == {}


def test_sequential_updates_accumulate_companies():
    """Simulate two sequential tools-node turns applied through the reducer."""
    state_data_cache = None

    # Turn 1: financials for AAPL
    turn1 = state_cache({"data_cache": state_data_cache})
    FinancialsCache._store(turn1, _mock_hf("AAPL", [2023, 2024]), span=2)
    state_data_cache = merge_cache(state_data_cache, turn1)

    # Turn 2: market data for MSFT
    turn2 = state_cache({"data_cache": state_data_cache})
    MarketDataCache._store(turn2, "MSFT", _mock_md(), include_rfr=True)
    state_data_cache = merge_cache(state_data_cache, turn2)

    assert set(state_data_cache["companies"]) == {"AAPL", "MSFT"}
    assert "financials" in state_data_cache["companies"]["AAPL"]["searched"]
    assert "market_data" in state_data_cache["companies"]["MSFT"]["searched"]


def test_parallel_branch_updates_merge_without_losing_either_side():
    """Two tool calls run on deep copies of the same base cache, then merge."""
    base = empty_data_cache()

    branch_a = deepcopy(base)
    FinancialsCache._store(branch_a, _mock_hf("AAPL", [2024]), span=1)

    branch_b = deepcopy(base)
    MarketDataCache._store(branch_b, "AAPL", _mock_md(), include_rfr=True)

    merged = merge_cache(merge_cache(base, branch_a), branch_b)

    company = merged["companies"]["AAPL"]
    assert "financials" in company["searched"]
    assert "market_data" in company["searched"]
    assert base["companies"] == {}  # base never mutated by the merge


def test_update_with_wider_coverage_overwrites_leaf():
    older = empty_data_cache()
    FinancialsCache._store(older, _mock_hf("AAPL", [2023, 2024]), span=2)

    newer = deepcopy(older)
    FinancialsCache._store(newer, _mock_hf("AAPL", [2020, 2021, 2022, 2023, 2024]), span=5)

    merged = merge_cache(older, newer)
    coverage = merged["companies"]["AAPL"]["searched"]["financials"]["coverage"]
    assert coverage["max_span"] == 5
    assert len(merged["companies"]["AAPL"]["searched"]["financials"]["periods_by_fiscal_year"]) == 5


def test_catalog_evolves_with_cache_updates():
    assert build_data_catalog(empty_data_cache()) == empty_data_catalog()

    cache = _cache_with_financials("AAPL", [2023, 2024])
    catalog = build_data_catalog(cache)
    assert len(catalog["companies"]) == 1
    entry = catalog["companies"][0]
    assert entry["ticker"] == "AAPL"
    assert entry["searched"]["financials"]["available"] is True
    assert entry["searched"]["financials"]["fiscal_years"] == ["2023", "2024"]
    assert entry["calculated"] == {}

    # A calculated result appears in the calculated bucket on the next build
    fake_liquidity = MagicMock(return_value={"current_ratio": [1.5]})
    with patch.dict(RatiosCache._RATIO_FUNCS, {"liquidity": fake_liquidity}):
        RatiosCache.get_or_calculate(cache, "AAPL", 2, "liquidity")
    catalog = build_data_catalog(cache)
    assert "ratios" in catalog["companies"][0]["calculated"]


def test_payload_contains_stored_data_for_response_node():
    cache = _cache_with_financials("AAPL", [2023, 2024])
    MarketDataCache._store(cache, "AAPL", _mock_md(), include_rfr=True)

    payload = build_data_payload(cache)
    assert "AAPL" in payload
    assert len(payload["AAPL"]["financials"]["periods"]) == 2
    assert payload["AAPL"]["market_data"]["current_price"] == 100.0


def test_payload_skips_companies_with_no_data():
    cache = empty_data_cache()
    cache["companies"]["EMPTY"] = {"ticker": "EMPTY", "name": None, "searched": {}, "calculated": {}}
    assert build_data_payload(cache) == {}
