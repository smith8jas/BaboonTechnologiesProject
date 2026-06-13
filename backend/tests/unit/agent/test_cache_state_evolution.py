"""Tests for the agent data-cache layer and for how cache state evolves.

Part 1 — cache classes: each get_or_fetch / get_or_calculate hits the external
service exactly once and serves repeats from the cache dict.

Part 2 — tool layer: tools write through the injected data_cache and report
"cache" vs "external" sources.

Part 3 — state evolution: the data_cache merges across sequential and parallel
node updates the way the LangGraph merge_cache reducer applies them, and the
catalog/payload views grow accordingly.

Part 4 — tools_node: end-to-end orchestration through the node interface.
Covers single calls, cache hits, parallel multi-ticker merges, the global
(no-ticker) path, and unknown-tool error handling.
"""

import asyncio
import json
from copy import deepcopy
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage

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


# ---------------------------------------------------------------------------
# Part 4 — tools_node: end-to-end orchestration through the node interface
# ---------------------------------------------------------------------------

from backend.agent.nodes.tools import tools_node


def _make_tools_state(tool_calls: list[dict], existing_cache: dict | None = None) -> dict:
    """Minimal AgentState sufficient for tools_node to run.

    tools_node only reads two things from state:
      - messages: scanned in reverse for the last AIMessage with tool_calls
      - data_cache: the current cache snapshot (absent → starts empty)
    """
    state = {
        # latest_tool_calls() walks messages in reverse and returns the
        # tool_calls list from the first AIMessage that has one
        "messages": [AIMessage(content="", tool_calls=tool_calls)],
        # required AgentState fields that tools_node itself does not read
        "context": "",
        "current_year": 2024,
        "available_tools": {},
    }
    if existing_cache is not None:
        # inject a pre-built cache so we can test cache-hit behaviour
        state["data_cache"] = existing_cache
    return state


def test_tools_node_single_call_populates_cache():
    """A single get_financials call populates data_cache and data_catalog."""
    state = _make_tools_state([
        # one tool call: name maps to TOOLS_BY_NAME, id is echoed on the ToolMessage
        {"name": "get_financials", "args": {"ticker": "AAPL", "span": 3}, "id": "tc_1"},
    ])

    with patch("backend.agent.cache.financials.financials_service") as mock_fin:
        # fake out the external data fetch so no real HTTP call is made
        mock_fin.get_cached_financials.return_value = _mock_hf("AAPL", [2022, 2023, 2024])
        # tools_node is a coroutine — asyncio.run() drives it synchronously
        result = asyncio.run(tools_node(state))

    # node must return all three keys
    assert "data_cache" in result
    assert "data_catalog" in result
    assert "messages" in result

    # AAPL financials should be stored under companies in the cache
    assert "AAPL" in result["data_cache"]["companies"]
    assert "financials" in result["data_cache"]["companies"]["AAPL"]["searched"]

    # catalog should reflect that AAPL is now available
    tickers = [entry["ticker"] for entry in result["data_catalog"]["companies"]]
    assert "AAPL" in tickers

    # exactly one ToolMessage, tied to the call id we passed in
    assert len(result["messages"]) == 1
    assert result["messages"][0].name == "get_financials"
    assert result["messages"][0].tool_call_id == "tc_1"


def test_tools_node_cache_hit_on_second_run():
    """When data_cache already holds the data, the tool reports source=cache and makes no external call."""
    # build a cache as if a previous turn had already fetched AAPL financials
    pre_cache = empty_data_cache()
    FinancialsCache._store(pre_cache, _mock_hf("AAPL", [2022, 2023, 2024]), span=3)

    # inject that pre-populated cache into the state
    state = _make_tools_state(
        [{"name": "get_financials", "args": {"ticker": "AAPL", "span": 3}, "id": "tc_2"}],
        existing_cache=pre_cache,
    )

    with patch("backend.agent.cache.financials.financials_service") as mock_fin:
        mock_fin.get_cached_financials.return_value = _mock_hf("AAPL", [2022, 2023, 2024])
        result = asyncio.run(tools_node(state))
        # the external service must not have been called — the cache handled it
        mock_fin.get_cached_financials.assert_not_called()

    # ToolMessage content should confirm the data came from cache, not external
    content = json.loads(result["messages"][0].content)
    assert content["source"] == "cache"


def test_tools_node_two_tickers_parallel_merge():
    """Two calls for different tickers run in parallel and both survive the branch merge."""
    state = _make_tools_state([
        # two calls with different tickers — _group_calls_by_ticker puts each in its own group
        {"name": "get_financials", "args": {"ticker": "AAPL", "span": 3}, "id": "tc_aapl"},
        {"name": "get_financials", "args": {"ticker": "MSFT", "span": 3}, "id": "tc_msft"},
    ])

    with patch("backend.agent.cache.financials.financials_service") as mock_fin:
        # side_effect lets us return ticker-specific data on each call
        mock_fin.get_cached_financials.side_effect = (
            lambda ticker, span, **_: _mock_hf(ticker, [2022, 2023, 2024])
        )
        result = asyncio.run(tools_node(state))

    cache = result["data_cache"]

    # both tickers must be present after the parallel-branch merge
    assert "AAPL" in cache["companies"]
    assert "MSFT" in cache["companies"]

    # one ToolMessage per call — order may vary since they ran in parallel
    assert len(result["messages"]) == 2
    call_ids = {msg.tool_call_id for msg in result["messages"]}
    assert call_ids == {"tc_aapl", "tc_msft"}


def test_tools_node_global_call_no_ticker():
    """get_sector_data has no ticker arg so it goes through the global-calls path, not a ticker group."""
    state = _make_tools_state([
        # year is the only arg — _group_calls_by_ticker keys this under None (global)
        {"name": "get_sector_data", "args": {"year": 2024}, "id": "tc_sector"},
    ])

    with patch("backend.agent.cache.sector_data.financials_service") as mock_sector:
        mock_sector.get_sector_data.return_value = _mock_sd()
        result = asyncio.run(tools_node(state))

    # sector data lives in cache["global"]["sector_data_by_year"], not under a company
    assert "2024" in result["data_cache"]["global"]["sector_data_by_year"]

    # single ToolMessage for the one call
    assert len(result["messages"]) == 1
    assert result["messages"][0].tool_call_id == "tc_sector"


def test_tools_node_unknown_tool_returns_error_message():
    """An unrecognised tool name produces a ToolMessage with error JSON rather than raising."""
    state = _make_tools_state([
        # name does not exist in TOOLS_BY_NAME
        {"name": "nonexistent_tool", "args": {}, "id": "tc_bad"},
    ])

    # no patch needed — the node handles missing tools internally
    result = asyncio.run(tools_node(state))

    # node must not raise; it should still return a ToolMessage for the call
    assert len(result["messages"]) == 1
    msg = result["messages"][0]
    assert msg.tool_call_id == "tc_bad"

    # content should be JSON with an "error" key and a list of valid tool names
    content = json.loads(msg.content)
    assert "error" in content
    assert "available_tools" in content
