"""Unit tests for the split tool-execution nodes (exec_research / exec_calc).

Covers:
- phase filtering: exec_research runs research only, exec_calc runs
  assumptions+calculation only
- exec_calc always refreshing data_catalog, even with no calls to run
- same-cycle visibility: exec_calc sees exec_research's delta through state
- scrape calls hard-filtered from both execution nodes
- scrape_web tool body as a thin transition layer over the scrape service
  (graph execution always routes scrape calls to scrape_node instead)
"""

import asyncio
import json
from unittest.mock import patch

from langchain_core.messages import AIMessage

from backend.agent.nodes.tools import exec_calc_node, exec_research_node
from backend.agent.tools import TOOLS_BY_NAME
from backend.processing.schema import HistoricalFinancials


def _mock_hf(ticker: str, fiscal_years: list[int]) -> HistoricalFinancials:
    return HistoricalFinancials.model_validate(
        {
            "ticker": ticker,
            "metadata": {"cik": "0000000001", "name": f"{ticker} Inc."},
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


def _state(tool_calls: list[dict], research_messages=None, calculated_messages=None) -> dict:
    return {
        "messages": [AIMessage(content="", tool_calls=tool_calls)],
        "context": "",
        "current_year": 2024,
        "available_tools": {},
        "research_messages": research_messages or [],
        "calculated_messages": calculated_messages or [],
        "query_count": 1,
    }


_MIXED_BATCH = [
    {"name": "get_financials", "args": {"ticker": "AAPL", "span": 3}, "id": "tc_fin"},
    {"name": "get_liquidity_ratios", "args": {"ticker": "AAPL", "span": 3}, "id": "tc_ratio"},
    {"name": "scrape_web", "args": {"topic": "AAPL news"}, "id": "tc_scrape"},
]


def test_exec_research_runs_only_research_calls():
    state = _state(_MIXED_BATCH)
    with patch("backend.agent.tools.research.financials_service") as mock_fin:
        mock_fin.get_cached_financials.return_value = _mock_hf("AAPL", [2022, 2023, 2024])
        result = asyncio.run(exec_research_node(state))

    # Only the research call executed — no ratio message, no scrape message
    assert [m.tool_call_id for m in result["messages"]] == ["tc_fin"]
    assert len(result["research_messages"]) == 1
    # exec_research never writes calculated_messages or data_catalog
    assert "calculated_messages" not in result
    assert "data_catalog" not in result


def test_exec_calc_runs_only_calculation_calls_and_sees_state_research():
    """exec_calc reads research written by exec_research through the state —
    the same-cycle visibility guarantee of the sequential topology."""
    state = _state(_MIXED_BATCH)
    with patch("backend.agent.tools.research.financials_service") as mock_fin:
        mock_fin.get_cached_financials.return_value = _mock_hf("AAPL", [2022, 2023, 2024])
        research_delta = asyncio.run(exec_research_node(state))

    # Simulate the superstep boundary: exec_research's delta lands in state
    state_after = {**state, "research_messages": research_delta["research_messages"]}

    with patch("backend.agent.tools.calculation.ratio_service") as mock_ratio:
        mock_ratio.get_liquidity_ratios.return_value = {"FY2024": {"current_ratio": 1.5}}
        result = asyncio.run(exec_calc_node(state_after))

    assert [m.tool_call_id for m in result["messages"]] == ["tc_ratio"]
    content = json.loads(result["messages"][0].content)
    assert content["source"] == "calculated"
    # exec_calc owns the catalog and it reflects both channels
    tickers = [e["ticker"] for e in result["data_catalog"]["companies"]]
    assert "AAPL" in tickers


def test_exec_calc_refreshes_catalog_even_without_calls():
    """Research-only cycles still need the catalog updated — exec_calc is its
    single writer and always rebuilds it from state."""
    existing_research = [{
        "tool": "get_financials", "identifier": ("financials", "AAPL"), "ticker": "AAPL",
        "cycle": 1, "last_updated": "2024-01-01T00:00:00+00:00",
        "data": _mock_hf("AAPL", [2023, 2024]).model_dump(mode="json"),
        "data_source": "Test source",
    }]
    state = _state(
        [{"name": "get_financials", "args": {"ticker": "AAPL"}, "id": "tc_fin"}],
        research_messages=existing_research,
    )
    result = asyncio.run(exec_calc_node(state))

    assert "data_catalog" in result
    tickers = [e["ticker"] for e in result["data_catalog"]["companies"]]
    assert "AAPL" in tickers
    # No calc calls ran, so no messages and no calculated_messages delta
    assert "calculated_messages" not in result
    assert not result.get("messages")


def test_exec_nodes_filter_scrape_calls():
    """A scrape-only batch is a no-op for both execution nodes (scrape_node owns it)."""
    state = _state([{"name": "scrape_web", "args": {"topic": "AAPL"}, "id": "tc_s"}])

    research_result = asyncio.run(exec_research_node(state))
    assert research_result == {}

    calc_result = asyncio.run(exec_calc_node(state))
    assert list(calc_result.keys()) == ["data_catalog"]


def test_scrape_web_direct_invocation_is_thin_service_layer():
    """Inside the graph scrape calls route to scrape_node; a direct invocation
    delegates to the scrape service (single query) and emits the same result
    shape scrape_node writes."""
    from backend.services.scrape import ScrapeResult

    hit = ScrapeResult(
        url="https://example.com/a", title="Example", snippet="text",
        confidence=0.9, source_type="news article",
    )

    async def fake_search(query, max_results, **kwargs):
        assert query == "AAPL news"
        assert max_results == 2
        return [hit]

    with patch("backend.agent.tools.research.search_and_scrape_async", side_effect=fake_search):
        result = TOOLS_BY_NAME["scrape_web"].invoke({"topic": "AAPL news", "max_results": 2})

    assert result["source"] == "web"
    assert result["results"] == [{
        "query": "AAPL news", "url": "https://example.com/a", "title": "Example",
        "snippet": "text", "confidence": 0.9, "source_type": "news article",
    }]
