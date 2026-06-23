"""Tests for the in-state research_messages/calculated_messages cache.

Part 1 — store primitive: find/upsert dedup-by-identifier, replace vs merge.
Part 2 — merge_financials_data: period union, metadata coalesce.
Part 3 — research tools: fetch-then-hit, span widening, fiscal_years coverage,
market_data RFR asymmetry, sector_data per-year.
Part 4 — calculation tools: CacheMissError when a dependency is missing, always
recompute (no staleness check), comps peer resolution / Damodaran fallback.
Part 5 — catalog and retention (purge).
Part 6 — tools_node: end-to-end orchestration through the node interface.
Part 7 — response_node: reads research/calculated messages directly.
"""

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from backend.agent.cache import CacheMissError, build_data_catalog, find, merge_financials_data, purge, tool_content, upsert
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
                    "fiscal_year": f"FY{y}",
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


def _mock_md(risk_free_rate: float | None = 0.04) -> MarketData:
    return MarketData(
        current_price=100.0,
        beta=1.1,
        shares_outstanding=1e9,
        market_cap=1e11,
        risk_free_rate=risk_free_rate,
    )


def _mock_sd() -> SectorData:
    return SectorData(equity_risk_premium=0.05, long_term_growth_rate=0.025)


def _entry(
    tool: str,
    identifier: tuple,
    ticker: str | None,
    data: dict,
    cycle: int = 1,
    data_source: str = "Test source",
) -> dict:
    return {
        "tool": tool, "identifier": identifier, "ticker": ticker,
        "cycle": cycle, "last_updated": "2024-01-01T00:00:00+00:00", "data": data,
        "data_source": data_source,
    }


# ---------------------------------------------------------------------------
# Part 1 — store primitive
# ---------------------------------------------------------------------------

def test_upsert_appends_new_entry():
    messages: list[dict] = []
    entry = upsert(messages, tool="get_financials", identifier=("financials", "AAPL"), ticker="AAPL", cycle=1, data={"a": 1}, data_source="Test source")
    assert messages == [entry]
    assert entry["data"] == {"a": 1}


def test_upsert_replaces_existing_entry_by_identifier():
    messages: list[dict] = []
    upsert(messages, tool="get_financials", identifier=("financials", "AAPL"), ticker="AAPL", cycle=1, data={"a": 1}, data_source="Test source")
    upsert(messages, tool="get_financials", identifier=("financials", "AAPL"), ticker="AAPL", cycle=2, data={"a": 2}, data_source="Test source")
    assert len(messages) == 1
    assert messages[0]["data"] == {"a": 2}
    assert messages[0]["cycle"] == 2


def test_upsert_merge_combines_old_and_new():
    messages: list[dict] = []
    combine = lambda old, new: {"v": old["v"] + new["v"]}
    upsert(messages, tool="t", identifier=("k", "X"), ticker="X", cycle=1, data={"v": [1]}, data_source="Test source", merge=combine)
    upsert(messages, tool="t", identifier=("k", "X"), ticker="X", cycle=2, data={"v": [2]}, data_source="Test source", merge=combine)
    assert len(messages) == 1
    assert messages[0]["data"]["v"] == [1, 2]


def test_find_returns_none_when_missing():
    assert find([], ("financials", "AAPL")) is None


def test_find_returns_matching_entry():
    messages = [_entry("get_financials", ("financials", "AAPL"), "AAPL", {"a": 1})]
    assert find(messages, ("financials", "AAPL")) is messages[0]


def test_find_matches_identifier_deserialized_as_list():
    # LangGraph's checkpointer round-trips state through a serializer with no
    # tuple type — entries that survive a turn boundary come back with a list
    # identifier even though tools always construct a fresh tuple to look up.
    messages = [_entry("get_financials", ["financials", "AAPL"], "AAPL", {"a": 1})]
    assert find(messages, ("financials", "AAPL")) is messages[0]


def test_upsert_replaces_list_identifier_entry_when_looked_up_by_tuple():
    messages = [_entry("get_financials", ["financials", "AAPL"], "AAPL", {"a": 1})]
    upsert(messages, tool="get_financials", identifier=("financials", "AAPL"), ticker="AAPL", cycle=2, data={"a": 2}, data_source="Test source")
    assert len(messages) == 1
    assert messages[0]["data"] == {"a": 2}


def test_upsert_is_safe_under_concurrent_writers_to_the_same_identifier():
    # tools_node now runs every call in a phase concurrently (real OS threads via
    # asyncio.to_thread), so two tool calls can race on the same identifier — e.g.
    # two get_financials calls for one ticker with different span/fiscal_years.
    # Without a lock, find-then-append is not atomic and concurrent writers can
    # produce duplicate entries instead of one deduped, merged entry.
    import threading

    messages: list[dict] = []
    barrier = threading.Barrier(20)

    def writer(n: int) -> None:
        barrier.wait()
        upsert(messages, tool="t", identifier=("k", "X"), ticker="X", cycle=n, data={"v": n}, data_source="Test source")

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(messages) == 1


# ---------------------------------------------------------------------------
# Part 2 — merge_financials_data
# ---------------------------------------------------------------------------

def test_merge_financials_unions_periods_by_fiscal_year():
    old = _mock_hf("AAPL", [2022, 2023]).model_dump(mode="json")
    new = _mock_hf("AAPL", [2023, 2024]).model_dump(mode="json")
    merged = merge_financials_data(old, new)
    assert {p["fiscal_year"] for p in merged["periods"]} == {"FY2022", "FY2023", "FY2024"}


def test_merge_financials_coalesces_metadata_nulls():
    old = {"ticker": "AAPL", "metadata": {"name": "Apple Inc.", "industry": "Tech"}, "periods": []}
    new = {"ticker": "AAPL", "metadata": {"name": "Apple Inc.", "industry": None}, "periods": []}
    merged = merge_financials_data(old, new)
    assert merged["metadata"]["industry"] == "Tech"


def test_merge_financials_new_value_wins_when_present():
    old = {"ticker": "AAPL", "metadata": {"industry": "Old"}, "periods": []}
    new = {"ticker": "AAPL", "metadata": {"industry": "New"}, "periods": []}
    merged = merge_financials_data(old, new)
    assert merged["metadata"]["industry"] == "New"


# ---------------------------------------------------------------------------
# Part 3 — research tools
# ---------------------------------------------------------------------------

from backend.agent.tools.research import get_financials, get_market_data, get_sector_data


def test_get_financials_tool_reports_external_then_cache():
    research_messages: list[dict] = []
    with patch("backend.agent.tools.research.financials_service") as mock_fin:
        mock_fin.get_cached_financials.return_value = _mock_hf("AAPL", [2022, 2023, 2024])
        first = get_financials.invoke({"ticker": "AAPL", "span": 3, "research_messages": research_messages, "cycle": 1})
        second = get_financials.invoke({"ticker": "AAPL", "span": 3, "research_messages": research_messages, "cycle": 1})
        assert mock_fin.get_cached_financials.call_count == 1
    assert first["source"] == "external"
    assert second["source"] == "cache"
    assert len(research_messages) == 1
    assert len(research_messages[0]["data"]["periods"]) == 3


def test_financials_wider_span_merges_with_existing():
    research_messages: list[dict] = []
    with patch("backend.agent.tools.research.financials_service") as mock_fin:
        mock_fin.get_cached_financials.return_value = _mock_hf("AAPL", [2023, 2024])
        get_financials.invoke({"ticker": "AAPL", "span": 2, "research_messages": research_messages, "cycle": 1})

        mock_fin.get_cached_financials.return_value = _mock_hf("AAPL", [2020, 2021, 2022, 2023, 2024])
        result = get_financials.invoke({"ticker": "AAPL", "span": 5, "research_messages": research_messages, "cycle": 1})

    assert result["source"] == "external"
    assert len(research_messages) == 1
    fiscal_years = {p["fiscal_year"] for p in research_messages[0]["data"]["periods"]}
    assert fiscal_years == {"FY2020", "FY2021", "FY2022", "FY2023", "FY2024"}


def test_financials_non_overlapping_fiscal_years_preserve_earlier_periods():
    """A later request for an older, non-overlapping year must not drop the periods
    a previous span-based fetch already established."""
    research_messages: list[dict] = []
    with patch("backend.agent.tools.research.financials_service") as mock_fin:
        mock_fin.get_cached_financials.return_value = _mock_hf("AAPL", [2022, 2023, 2024])
        get_financials.invoke({"ticker": "AAPL", "span": 3, "research_messages": research_messages, "cycle": 1})

        mock_fin.get_cached_financials.return_value = _mock_hf("AAPL", [2017, 2018])
        get_financials.invoke(
            {"ticker": "AAPL", "span": 3, "fiscal_years": [2018], "research_messages": research_messages, "cycle": 1}
        )

    assert len(research_messages) == 1
    fiscal_years = {p["fiscal_year"] for p in research_messages[0]["data"]["periods"]}
    assert fiscal_years == {"FY2017", "FY2018", "FY2022", "FY2023", "FY2024"}


def test_financials_fiscal_years_cache_hit_does_not_call_external():
    research_messages: list[dict] = []
    with patch("backend.agent.tools.research.financials_service") as mock_fin:
        mock_fin.get_cached_financials.return_value = _mock_hf("AAPL", [2020, 2021, 2022, 2023, 2024])
        get_financials.invoke({"ticker": "AAPL", "span": 5, "research_messages": research_messages, "cycle": 1})
        mock_fin.reset_mock()
        result = get_financials.invoke(
            {"ticker": "AAPL", "fiscal_years": [2021, 2022], "research_messages": research_messages, "cycle": 1}
        )
        mock_fin.get_cached_financials.assert_not_called()
    assert result["source"] == "cache"


def test_financials_normalizes_missing_fiscal_year():
    research_messages: list[dict] = []
    hf = _mock_hf("AAPL", [2023])
    hf.periods[0].fiscal_year = None
    with patch("backend.agent.tools.research.financials_service") as mock_fin:
        mock_fin.get_cached_financials.return_value = hf
        get_financials.invoke({"ticker": "AAPL", "span": 1, "research_messages": research_messages, "cycle": 1})
    assert research_messages[0]["data"]["periods"][0]["fiscal_year"] == "FY2023"


def test_market_data_fetch_then_hit():
    research_messages: list[dict] = []
    with patch("backend.agent.tools.research.financials_service") as mock_fin:
        mock_fin.get_market_data.return_value = _mock_md()
        first = get_market_data.invoke({"ticker": "AAPL", "include_rfr": True, "research_messages": research_messages, "cycle": 1})
        second = get_market_data.invoke({"ticker": "AAPL", "include_rfr": True, "research_messages": research_messages, "cycle": 1})
        assert mock_fin.get_market_data.call_count == 1
    assert first["source"] == "external"
    assert second["source"] == "cache"


def test_market_data_without_rfr_does_not_satisfy_rfr_request():
    research_messages: list[dict] = []
    with patch("backend.agent.tools.research.financials_service") as mock_fin:
        mock_fin.get_market_data.return_value = _mock_md(risk_free_rate=None)
        get_market_data.invoke({"ticker": "AAPL", "include_rfr": False, "research_messages": research_messages, "cycle": 1})

        mock_fin.get_market_data.return_value = _mock_md(risk_free_rate=0.04)
        second = get_market_data.invoke({"ticker": "AAPL", "include_rfr": True, "research_messages": research_messages, "cycle": 1})
        assert mock_fin.get_market_data.call_count == 2
    assert second["source"] == "external"


def test_market_data_with_rfr_satisfies_no_rfr_request():
    research_messages: list[dict] = []
    with patch("backend.agent.tools.research.financials_service") as mock_fin:
        mock_fin.get_market_data.return_value = _mock_md(risk_free_rate=0.04)
        get_market_data.invoke({"ticker": "AAPL", "include_rfr": True, "research_messages": research_messages, "cycle": 1})
        second = get_market_data.invoke({"ticker": "AAPL", "include_rfr": False, "research_messages": research_messages, "cycle": 1})
        assert mock_fin.get_market_data.call_count == 1
    assert second["source"] == "cache"


def test_sector_data_cached_per_year():
    research_messages: list[dict] = []
    with patch("backend.agent.tools.research.financials_service") as mock_fin:
        mock_fin.get_sector_data.return_value = _mock_sd()
        first = get_sector_data.invoke({"year": 2024, "research_messages": research_messages, "cycle": 1})
        second = get_sector_data.invoke({"year": 2024, "research_messages": research_messages, "cycle": 1})
        third = get_sector_data.invoke({"year": 2023, "research_messages": research_messages, "cycle": 1})
        assert mock_fin.get_sector_data.call_count == 2
    assert (first["source"], second["source"], third["source"]) == ("external", "cache", "external")
    assert len(research_messages) == 2


# ---------------------------------------------------------------------------
# Part 4 — calculation tools
# ---------------------------------------------------------------------------

from backend.agent.tools.calculation import (
    get_comps_valuation,
    get_income_statement_growth_rates,
    get_liquidity_ratios,
    run_dcf_valuation,
)


def test_growth_raises_cache_miss_without_financials():
    with pytest.raises(CacheMissError):
        get_income_statement_growth_rates.invoke(
            {"ticker": "AAPL", "span": 5, "research_messages": [], "calculated_messages": []}
        )


def test_growth_calculates_from_research_messages_without_external_call():
    research_messages = [
        _entry("get_financials", ("financials", "AAPL"), "AAPL", _mock_hf("AAPL", [2020, 2021, 2022, 2023, 2024]).model_dump(mode="json"))
    ]
    calculated_messages: list[dict] = []
    with patch("backend.agent.tools.calculation.growth_service") as mock_growth:
        mock_growth.get_income_statement_growth_rates.return_value = {"FY2024": {"revenue": 0.1}}
        result = get_income_statement_growth_rates.invoke({
            "ticker": "AAPL", "span": 5,
            "research_messages": research_messages, "calculated_messages": calculated_messages, "cycle": 1,
        })
    assert result["source"] == "calculated"
    assert calculated_messages[0]["identifier"] == ("growth", "AAPL", "income_statement")


def test_ratios_always_recompute_but_dedupe_identifier():
    """Recompute is free — every call recalculates, but only one entry survives per identifier."""
    research_messages = [
        _entry("get_financials", ("financials", "AAPL"), "AAPL", _mock_hf("AAPL", [2020, 2021, 2022, 2023, 2024]).model_dump(mode="json"))
    ]
    calculated_messages: list[dict] = []
    with patch("backend.agent.tools.calculation.ratio_service") as mock_ratio:
        mock_ratio.get_liquidity_ratios.return_value = {"FY2024": {"current_ratio": 1.5}}
        get_liquidity_ratios.invoke({
            "ticker": "AAPL", "span": 5,
            "research_messages": research_messages, "calculated_messages": calculated_messages, "cycle": 1,
        })
        get_liquidity_ratios.invoke({
            "ticker": "AAPL", "span": 5,
            "research_messages": research_messages, "calculated_messages": calculated_messages, "cycle": 2,
        })
        assert mock_ratio.get_liquidity_ratios.call_count == 2
    assert len(calculated_messages) == 1


def test_dcf_requires_all_three_dependencies():
    with pytest.raises(CacheMissError):
        run_dcf_valuation.invoke({
            "ticker": "AAPL", "span": 5, "year": 2024,
            "research_messages": [], "calculated_messages": [],
        })


def test_dcf_computes_from_research_messages():
    research_messages = [
        _entry("get_financials", ("financials", "AAPL"), "AAPL", _mock_hf("AAPL", [2020, 2021, 2022, 2023, 2024]).model_dump(mode="json")),
        _entry("get_market_data", ("market_data", "AAPL"), "AAPL", _mock_md().model_dump(mode="json")),
        _entry("get_sector_data", ("sector_data", 2024), None, _mock_sd().model_dump(mode="json")),
    ]
    calculated_messages: list[dict] = []
    dcf_result = MagicMock()
    dcf_result.model_dump.return_value = {"fiscal_year": "FY2024", "intrinsic_value_per_share": 123.0}
    with patch("backend.agent.tools.calculation.dcf_engine") as mock_engine:
        mock_engine.run_dcf.return_value = dcf_result
        result = run_dcf_valuation.invoke({
            "ticker": "AAPL", "span": 5, "year": 2024,
            "research_messages": research_messages, "calculated_messages": calculated_messages, "cycle": 1,
        })
    assert result["data"]["intrinsic_value_per_share"] == 123.0
    assert calculated_messages[0]["identifier"] == ("dcf", "AAPL", "default")


def test_comps_peer_drops_unresolved_peers():
    research_messages = [
        _entry("get_financials", ("financials", "AAPL"), "AAPL", _mock_hf("AAPL", [2024]).model_dump(mode="json")),
        _entry("get_market_data", ("market_data", "AAPL"), "AAPL", _mock_md().model_dump(mode="json")),
        _entry("get_financials", ("financials", "MSFT"), "MSFT", _mock_hf("MSFT", [2024]).model_dump(mode="json")),
        _entry("get_market_data", ("market_data", "MSFT"), "MSFT", _mock_md().model_dump(mode="json")),
        # GOOGL has no research data at all — must be dropped, not fetched.
    ]
    calculated_messages: list[dict] = []
    with patch("backend.agent.tools.calculation.comparables_service") as mock_comps:
        mock_comps.peer_comps.return_value = {"source": "peer comparables", "peers_used": ["MSFT"]}
        get_comps_valuation.invoke({
            "ticker": "AAPL", "peers": ["MSFT", "GOOGL"],
            "research_messages": research_messages, "calculated_messages": calculated_messages, "cycle": 1,
        })

    resolved_peers, dropped = mock_comps.peer_comps.call_args[0][2], mock_comps.peer_comps.call_args[0][3]
    assert [p[0] for p in resolved_peers] == ["MSFT"]
    assert dropped[0]["ticker"] == "GOOGL"


def test_comps_damodaran_fetches_once_then_reuses_sector_multiples():
    research_messages = [
        _entry("get_financials", ("financials", "AAPL"), "AAPL", _mock_hf("AAPL", [2024]).model_dump(mode="json")),
        _entry("get_market_data", ("market_data", "AAPL"), "AAPL", _mock_md().model_dump(mode="json")),
    ]
    calculated_messages: list[dict] = []

    with (
        patch("backend.agent.tools.calculation.comparables_service") as mock_comps,
        patch("backend.adapters.damodaran.fetch_ev_sales", return_value=2.0),
        patch("backend.adapters.damodaran.fetch_price_sales", return_value=3.0),
        patch("backend.adapters.damodaran.fetch_trailing_pe", return_value=20.0) as mock_pe,
    ):
        mock_comps.resolve_damodaran_industry.return_value = ("Software", [])
        mock_comps.damodaran_fallback.return_value = {"source": "Damodaran sector median"}
        get_comps_valuation.invoke({
            "ticker": "AAPL",
            "research_messages": research_messages, "calculated_messages": calculated_messages, "cycle": 1,
        })
        assert mock_pe.call_count == 1

    assert any(e["identifier"] == ("damodaran_sector", "Software") for e in research_messages)

    with (
        patch("backend.agent.tools.calculation.comparables_service") as mock_comps2,
        patch("backend.adapters.damodaran.fetch_trailing_pe") as mock_pe2,
    ):
        mock_comps2.resolve_damodaran_industry.return_value = ("Software", [])
        mock_comps2.damodaran_fallback.return_value = {"source": "Damodaran sector median"}
        get_comps_valuation.invoke({
            "ticker": "AAPL",
            "research_messages": research_messages, "calculated_messages": calculated_messages, "cycle": 2,
        })
        mock_pe2.assert_not_called()


def test_tool_content_serializes_models_and_dicts():
    assert '"source"' in tool_content({"source": "cache"})
    assert '"current_price"' in tool_content(_mock_md())


# ---------------------------------------------------------------------------
# Part 5 — catalog and retention
# ---------------------------------------------------------------------------

def test_catalog_empty_when_no_data():
    assert build_data_catalog([], []) == {"companies": [], "global": {"sector_data_years": []}}


def test_catalog_reflects_research_and_calculated_messages():
    research_messages = [
        _entry("get_financials", ("financials", "AAPL"), "AAPL", _mock_hf("AAPL", [2023, 2024]).model_dump(mode="json"))
    ]
    calculated_messages: list[dict] = []

    catalog = build_data_catalog(research_messages, calculated_messages)
    assert len(catalog["companies"]) == 1
    entry = catalog["companies"][0]
    assert entry["ticker"] == "AAPL"
    assert entry["searched"]["financials"]["available"] is True
    assert set(entry["searched"]["financials"]["fiscal_years"]) == {"FY2023", "FY2024"}
    assert entry["calculated"] == {}

    calculated_messages.append(
        _entry("get_liquidity_ratios", ("ratios", "AAPL", "liquidity"), "AAPL", {"FY2024": {"current_ratio": 1.5}})
    )
    catalog = build_data_catalog(research_messages, calculated_messages)
    assert "liquidity" in catalog["companies"][0]["calculated"]["ratios"]


def test_catalog_sector_data_years_is_global_not_per_company():
    research_messages = [_entry("get_sector_data", ("sector_data", 2024), None, {"equity_risk_premium": 0.05})]
    catalog = build_data_catalog(research_messages, [])
    assert catalog["global"]["sector_data_years"] == [2024]
    assert catalog["companies"] == []


def test_purge_drops_entries_past_retention():
    research_messages = [_entry("get_financials", ("financials", "AAPL"), "AAPL", {}, cycle=1)]
    calculated_messages = [_entry("get_liquidity_ratios", ("ratios", "AAPL", "liquidity"), "AAPL", {}, cycle=1)]
    new_research, new_calculated = purge(research_messages, calculated_messages, current_cycle=10)
    assert new_research == []
    assert new_calculated == []


def test_purge_keeps_recent_entries():
    research_messages = [_entry("get_financials", ("financials", "AAPL"), "AAPL", {}, cycle=9)]
    calculated_messages = [_entry("get_liquidity_ratios", ("ratios", "AAPL", "liquidity"), "AAPL", {}, cycle=9)]
    new_research, new_calculated = purge(research_messages, calculated_messages, current_cycle=10)
    assert len(new_research) == 1
    assert len(new_calculated) == 1


def test_purge_is_a_no_op_before_threshold():
    research_messages = [_entry("get_financials", ("financials", "AAPL"), "AAPL", {}, cycle=1)]
    new_research, _ = purge(research_messages, [], current_cycle=2)
    assert len(new_research) == 1


# ---------------------------------------------------------------------------
# Part 6 — tools_node: end-to-end orchestration through the node interface
# ---------------------------------------------------------------------------

from backend.agent.nodes.tools import tools_node


def _make_tools_state(tool_calls: list[dict], research_messages=None, calculated_messages=None, query_count: int = 1) -> dict:
    """Minimal AgentState sufficient for tools_node to run."""
    return {
        "messages": [AIMessage(content="", tool_calls=tool_calls)],
        "context": "",
        "current_year": 2024,
        "available_tools": {},
        "research_messages": research_messages or [],
        "calculated_messages": calculated_messages or [],
        "query_count": query_count,
    }


def test_tools_node_single_call_populates_research_messages():
    """A single get_financials call writes into research_messages and updates data_catalog."""
    state = _make_tools_state([{"name": "get_financials", "args": {"ticker": "AAPL", "span": 3}, "id": "tc_1"}])
    with patch("backend.agent.tools.research.financials_service") as mock_fin:
        mock_fin.get_cached_financials.return_value = _mock_hf("AAPL", [2022, 2023, 2024])
        result = asyncio.run(tools_node(state))

    assert "data_catalog" in result
    assert "messages" in result
    assert len(result["research_messages"]) == 1
    assert result["research_messages"][0]["identifier"] == ("financials", "AAPL")

    tickers = [e["ticker"] for e in result["data_catalog"]["companies"]]
    assert "AAPL" in tickers

    assert len(result["messages"]) == 1
    assert result["messages"][0].name == "get_financials"
    assert result["messages"][0].tool_call_id == "tc_1"


def test_tools_node_cache_hit_on_second_run():
    """When research_messages already holds the data, the tool reports source=cache and makes no external call."""
    existing = [_entry("get_financials", ("financials", "AAPL"), "AAPL", _mock_hf("AAPL", [2022, 2023, 2024]).model_dump(mode="json"))]
    state = _make_tools_state(
        [{"name": "get_financials", "args": {"ticker": "AAPL", "span": 3}, "id": "tc_2"}],
        research_messages=existing,
    )

    with patch("backend.agent.tools.research.financials_service") as mock_fin:
        result = asyncio.run(tools_node(state))
        mock_fin.get_cached_financials.assert_not_called()

    content = json.loads(result["messages"][0].content)
    assert content["source"] == "cache"


def test_tools_node_two_tickers_parallel_writes():
    """Two calls for different tickers run concurrently and both land in research_messages."""
    state = _make_tools_state([
        {"name": "get_financials", "args": {"ticker": "AAPL", "span": 3}, "id": "tc_aapl"},
        {"name": "get_financials", "args": {"ticker": "MSFT", "span": 3}, "id": "tc_msft"},
    ])

    with patch("backend.agent.tools.research.financials_service") as mock_fin:
        mock_fin.get_cached_financials.side_effect = lambda ticker, span, **_: _mock_hf(ticker, [2022, 2023, 2024])
        result = asyncio.run(tools_node(state))

    tickers_in_research = {e["ticker"] for e in result["research_messages"]}
    assert {"AAPL", "MSFT"}.issubset(tickers_in_research)

    assert len(result["messages"]) == 2
    call_ids = {msg.tool_call_id for msg in result["messages"]}
    assert call_ids == {"tc_aapl", "tc_msft"}


def test_tools_node_calculation_sees_same_call_research_results():
    """Financials fetched in phase 1 must be visible to a calculation tool in phase 2
    of the same tools_node call, before either list is persisted to AgentState."""
    state = _make_tools_state([
        {"name": "get_financials", "args": {"ticker": "AAPL", "span": 5}, "id": "tc_fin"},
        {"name": "get_liquidity_ratios", "args": {"ticker": "AAPL", "span": 5}, "id": "tc_ratio"},
    ])

    with (
        patch("backend.agent.tools.research.financials_service") as mock_fin,
        patch("backend.agent.tools.calculation.ratio_service") as mock_ratio,
    ):
        mock_fin.get_cached_financials.return_value = _mock_hf("AAPL", [2020, 2021, 2022, 2023, 2024])
        mock_ratio.get_liquidity_ratios.return_value = {"FY2024": {"current_ratio": 1.5}}
        result = asyncio.run(tools_node(state))

    ratio_msg = next(m for m in result["messages"] if m.tool_call_id == "tc_ratio")
    content = json.loads(ratio_msg.content)
    assert content["source"] == "calculated"
    assert content["data"] == {"FY2024": {"current_ratio": 1.5}}


def test_tools_node_global_call_no_ticker():
    """get_sector_data has no ticker arg so it goes through the global-calls path."""
    state = _make_tools_state([{"name": "get_sector_data", "args": {"year": 2024}, "id": "tc_sector"}])

    with patch("backend.agent.tools.research.financials_service") as mock_sector:
        mock_sector.get_sector_data.return_value = _mock_sd()
        result = asyncio.run(tools_node(state))

    assert any(e["identifier"] == ("sector_data", 2024) for e in result["research_messages"])
    assert result["data_catalog"]["global"]["sector_data_years"] == [2024]
    assert len(result["messages"]) == 1
    assert result["messages"][0].tool_call_id == "tc_sector"


def test_tools_node_unknown_tool_returns_error_message():
    """An unrecognised tool name produces a ToolMessage with error JSON rather than raising."""
    state = _make_tools_state([{"name": "nonexistent_tool", "args": {}, "id": "tc_bad"}])

    result = asyncio.run(tools_node(state))

    assert len(result["messages"]) == 1
    msg = result["messages"][0]
    assert msg.tool_call_id == "tc_bad"

    content = json.loads(msg.content)
    assert "error" in content
    assert "available_tools" in content


# ---------------------------------------------------------------------------
# Part 7 — response_node reads research/calculated messages directly
# ---------------------------------------------------------------------------

from backend.agent.nodes.response import _methodology_notes, _project, _sanitize_internal_names


def test_response_project_drops_bookkeeping_fields():
    entries = [_entry("get_financials", ("financials", "AAPL"), "AAPL", {"periods": []}, cycle=3)]
    projected = _project(entries)
    assert projected == [
        {
            "ticker": "AAPL",
            "identifier": ("financials", "AAPL"),
            "data": {"periods": []},
            "data_source": "Test source",
            "methodology_label": "Financial statement data",
        }
    ]
    assert "cycle" not in projected[0]
    assert "tool" not in projected[0]
    assert "last_updated" not in projected[0]


def test_response_methodology_notes_use_public_labels_and_sanitized_text():
    entries = [
        _entry("get_financials", ("financials", "AAPL"), "AAPL", {"periods": []}),
        _entry("run_dcf_valuation", ("dcf", "AAPL", "default"), "AAPL", {"intrinsic_value_per_share": 100}),
    ]

    notes = _methodology_notes(entries)

    assert "Financial statement data" in notes
    assert "DCF valuation model" in notes
    joined = json.dumps(notes)
    assert "get_financials" not in joined
    assert "run_dcf_valuation" not in joined


def test_response_sanitizes_legacy_internal_function_names():
    text = _sanitize_internal_names("Per dcf_func and run_dcf_valuation, this uses get_financials(ticker, span).")

    assert "dcf_func" not in text
    assert "run_dcf_valuation" not in text
    assert "get_financials" not in text
    assert "DCF valuation model" in text


def test_response_node_payload_contains_full_history_not_just_latest_round():
    """response_node must see everything in research_messages/calculated_messages,
    not just whatever the most recent tool-calling round produced."""
    from backend.agent.nodes.response import response_node

    state = {
        "messages": [],
        "dialogue": [],
        "context": "",
        "research_messages": [
            _entry("get_financials", ("financials", "AAPL"), "AAPL", _mock_hf("AAPL", [2023, 2024]).model_dump(mode="json")),
            _entry("get_financials", ("financials", "MSFT"), "MSFT", _mock_hf("MSFT", [2023, 2024]).model_dump(mode="json")),
        ],
        "calculated_messages": [],
    }

    captured = {}

    async def fake_invoke_llm(state, prompt, node, data_payload=None):
        captured["payload"] = data_payload
        return AIMessage(content="ok")

    with patch("backend.agent.nodes.response.invoke_llm", fake_invoke_llm):
        asyncio.run(response_node(state))

    tickers_seen = {e["ticker"] for e in captured["payload"]["research"]}
    assert tickers_seen == {"AAPL", "MSFT"}
    joined = json.dumps(captured["payload"], default=str)
    assert "get_financials" not in joined
    assert "methodology" in captured["payload"]
