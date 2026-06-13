"""Tests for the DuckDB-backed agent cache layer and for how cache state evolves.

Part 1 — cache classes: each get_or_fetch / get_or_calculate hits the external
service exactly once and serves repeats from DuckDB.

Part 2 — tool layer: tools write through the injected session_id and report
"cache" vs "external" sources.

Part 3 — state evolution: concurrent writes both land in DuckDB, and the
catalog/payload views grow accordingly.

Part 4 — tools_node: end-to-end orchestration through the node interface.
Covers single calls, cache hits, parallel multi-ticker writes, the global
(no-ticker) path, and unknown-tool error handling.
"""

import asyncio
import json
import uuid
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
    tool_content,
)
from backend.agent.cache.schema import SUBDOMAIN_INCOME_STATEMENT
from backend.agent.cache.session import close_session, create_session, open_connection
from backend.processing.schema import HistoricalFinancials, MarketData, SectorData


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def _new_session() -> str:
    sid = f"test_{uuid.uuid4().hex[:8]}"
    create_session(sid)
    return sid


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


def _session_with_financials(ticker: str, fiscal_years: list[int]) -> tuple[str, object]:
    """Return (session_id, open_conn) pre-loaded with financials for ticker."""
    sid = _new_session()
    conn = open_connection(sid)
    FinancialsCache._store(conn, _mock_hf(ticker, fiscal_years), span=len(fiscal_years))
    return sid, conn


# ---------------------------------------------------------------------------
# Part 1 — cache classes fetch once, then reuse
# ---------------------------------------------------------------------------

def test_financials_fetch_then_hit():
    sid = _new_session()
    try:
        with patch("backend.agent.cache.financials.financials_service") as mock_fin:
            mock_fin.get_cached_financials.return_value = _mock_hf("AAPL", [2022, 2023, 2024])

            conn = open_connection(sid)
            _, first_cached = FinancialsCache.get_or_fetch(conn, "AAPL", span=3)
            conn.close()

            conn = open_connection(sid)
            _, second_cached = FinancialsCache.get_or_fetch(conn, "AAPL", span=3)
            conn.close()

            assert mock_fin.get_cached_financials.call_count == 1
        assert (first_cached, second_cached) == (False, True)
    finally:
        close_session(sid)


def test_financials_wider_span_refetches():
    sid, conn = _session_with_financials("AAPL", [2023, 2024])
    try:
        with patch("backend.agent.cache.financials.financials_service") as mock_fin:
            mock_fin.get_cached_financials.return_value = _mock_hf("AAPL", [2020, 2021, 2022, 2023, 2024])
            _, was_cached = FinancialsCache.get_or_fetch(conn, "AAPL", span=5)
            mock_fin.get_cached_financials.assert_called_once_with("AAPL", 5)
        assert was_cached is False
    finally:
        conn.close()
        close_session(sid)


def test_market_data_fetch_then_hit():
    sid = _new_session()
    try:
        with patch("backend.agent.cache.market_data.financials_service") as mock_fin:
            mock_fin.get_market_data.return_value = _mock_md()

            conn = open_connection(sid)
            _, first_cached = MarketDataCache.get_or_fetch(conn, "AAPL", include_rfr=True)
            conn.close()

            conn = open_connection(sid)
            _, second_cached = MarketDataCache.get_or_fetch(conn, "AAPL", include_rfr=True)
            conn.close()

            assert mock_fin.get_market_data.call_count == 1
        assert (first_cached, second_cached) == (False, True)
    finally:
        close_session(sid)


def test_market_data_without_rfr_does_not_satisfy_rfr_request():
    sid = _new_session()
    try:
        with patch("backend.agent.cache.market_data.financials_service") as mock_fin:
            mock_fin.get_market_data.return_value = _mock_md()

            conn = open_connection(sid)
            MarketDataCache.get_or_fetch(conn, "AAPL", include_rfr=False)
            _, was_cached = MarketDataCache.get_or_fetch(conn, "AAPL", include_rfr=True)
            conn.close()

            assert mock_fin.get_market_data.call_count == 2
        assert was_cached is False
    finally:
        close_session(sid)


def test_market_data_with_rfr_satisfies_no_rfr_request():
    sid = _new_session()
    try:
        with patch("backend.agent.cache.market_data.financials_service") as mock_fin:
            mock_fin.get_market_data.return_value = _mock_md()

            conn = open_connection(sid)
            MarketDataCache.get_or_fetch(conn, "AAPL", include_rfr=True)
            _, was_cached = MarketDataCache.get_or_fetch(conn, "AAPL", include_rfr=False)
            conn.close()

            assert mock_fin.get_market_data.call_count == 1
        assert was_cached is True
    finally:
        close_session(sid)


def test_sector_data_cached_per_year():
    sid = _new_session()
    try:
        with patch("backend.agent.cache.sector_data.financials_service") as mock_fin:
            mock_fin.get_sector_data.return_value = _mock_sd()

            conn = open_connection(sid)
            _, first_cached = SectorDataCache.get_or_fetch(conn, 2024)
            _, second_cached = SectorDataCache.get_or_fetch(conn, 2024)
            _, other_year_cached = SectorDataCache.get_or_fetch(conn, 2023)
            conn.close()

            assert mock_fin.get_sector_data.call_count == 2
        assert (first_cached, second_cached, other_year_cached) == (False, True, False)
    finally:
        close_session(sid)


def test_growth_calculates_from_cached_financials_without_external_call():
    sid, conn = _session_with_financials("AAPL", [2020, 2021, 2022, 2023, 2024])
    try:
        with (
            patch("backend.agent.cache.financials.financials_service") as mock_fin,
            patch("backend.agent.cache.growth.growth_service") as mock_growth,
        ):
            mock_growth.get_income_statement_growth_rates.return_value = {"revenue": [0.1]}

            _, first_cached = GrowthCache.get_or_calculate(conn, "AAPL", 5, SUBDOMAIN_INCOME_STATEMENT)
            _, second_cached = GrowthCache.get_or_calculate(conn, "AAPL", 5, SUBDOMAIN_INCOME_STATEMENT)

            mock_fin.get_cached_financials.assert_not_called()
            assert mock_growth.get_income_statement_growth_rates.call_count == 1
        assert (first_cached, second_cached) == (False, True)
    finally:
        conn.close()
        close_session(sid)


def test_ratios_calculate_once_then_reuse():
    sid, conn = _session_with_financials("AAPL", [2020, 2021, 2022, 2023, 2024])
    fake_liquidity = MagicMock(return_value={"current_ratio": [1.5]})
    try:
        with patch.dict(RatiosCache._RATIO_FUNCS, {"liquidity": fake_liquidity}):
            _, first_cached = RatiosCache.get_or_calculate(conn, "AAPL", 5, "liquidity")
            _, second_cached = RatiosCache.get_or_calculate(conn, "AAPL", 5, "liquidity")

            assert fake_liquidity.call_count == 1
        assert (first_cached, second_cached) == (False, True)
    finally:
        conn.close()
        close_session(sid)


def test_ratios_narrower_span_is_satisfied_by_wider_coverage():
    sid, conn = _session_with_financials("AAPL", [2020, 2021, 2022, 2023, 2024])
    fake_liquidity = MagicMock(return_value={"current_ratio": [1.5]})
    try:
        with patch.dict(RatiosCache._RATIO_FUNCS, {"liquidity": fake_liquidity}):
            RatiosCache.get_or_calculate(conn, "AAPL", 5, "liquidity")
            _, was_cached = RatiosCache.get_or_calculate(conn, "AAPL", 3, "liquidity")
        assert was_cached is True
    finally:
        conn.close()
        close_session(sid)


def test_dcf_calculates_once_then_reuses_for_same_span_and_year():
    sid, conn = _session_with_financials("AAPL", [2020, 2021, 2022, 2023, 2024])
    dcf_result = MagicMock(fiscal_year="FY2024", projection_years=["FY2025"])
    dcf_result.model_dump.return_value = {
        "fiscal_year": "FY2024",
        "projection_years": ["FY2025"],
        "intrinsic_value_per_share": 123.0,
    }
    try:
        with (
            patch("backend.agent.cache.market_data.financials_service") as mock_fin,
            patch("backend.agent.cache.sector_data.financials_service") as mock_sector,
            patch("backend.agent.cache.dcf.dcf_engine") as mock_engine,
        ):
            mock_fin.get_market_data.return_value = _mock_md()
            mock_sector.get_sector_data.return_value = _mock_sd()
            mock_engine.run_dcf.return_value = dcf_result

            payload, first_cached = DCFCache.get_or_calculate(conn, "AAPL", 5, 2024)
            _, second_cached = DCFCache.get_or_calculate(conn, "AAPL", 5, 2024)

            assert mock_engine.run_dcf.call_count == 1
        assert (first_cached, second_cached) == (False, True)
        assert payload["intrinsic_value_per_share"] == 123.0
    finally:
        conn.close()
        close_session(sid)


def test_dcf_different_sector_year_recalculates():
    sid, conn = _session_with_financials("AAPL", [2020, 2021, 2022, 2023, 2024])
    dcf_result = MagicMock(fiscal_year="FY2024", projection_years=["FY2025"])
    dcf_result.model_dump.return_value = {"fiscal_year": "FY2024", "projection_years": ["FY2025"]}
    try:
        with (
            patch("backend.agent.cache.market_data.financials_service") as mock_fin,
            patch("backend.agent.cache.sector_data.financials_service") as mock_sector,
            patch("backend.agent.cache.dcf.dcf_engine") as mock_engine,
        ):
            mock_fin.get_market_data.return_value = _mock_md()
            mock_sector.get_sector_data.return_value = _mock_sd()
            mock_engine.run_dcf.return_value = dcf_result

            DCFCache.get_or_calculate(conn, "AAPL", 5, 2024)
            _, was_cached = DCFCache.get_or_calculate(conn, "AAPL", 5, 2023)

            assert mock_engine.run_dcf.call_count == 2
        assert was_cached is False
    finally:
        conn.close()
        close_session(sid)


def test_comps_peer_reuses_for_same_peer_set_recomputes_for_new():
    sid = _new_session()
    try:
        with patch("backend.agent.cache.comparables.comparables_service") as mock_comps:
            mock_comps.peer_comps.return_value = {"source": "peer comparables"}

            conn = open_connection(sid)
            _, first_cached = CompsCache.get_or_calculate_peer(conn, "AAPL", ["MSFT", "GOOGL"])
            _, reordered_cached = CompsCache.get_or_calculate_peer(conn, "AAPL", ["googl", "msft"])
            _, new_peers_cached = CompsCache.get_or_calculate_peer(conn, "AAPL", ["MSFT"])
            conn.close()

            assert mock_comps.peer_comps.call_count == 2
        assert (first_cached, reordered_cached, new_peers_cached) == (False, True, False)
    finally:
        close_session(sid)


def test_comps_damodaran_cached_after_first_call():
    sid = _new_session()
    try:
        with patch("backend.agent.cache.comparables.comparables_service") as mock_comps:
            mock_comps.damodaran_fallback.return_value = {"source": "damodaran"}

            conn = open_connection(sid)
            _, first_cached = CompsCache.get_or_calculate_damodaran(conn, "AAPL")
            _, second_cached = CompsCache.get_or_calculate_damodaran(conn, "AAPL")
            conn.close()

            assert mock_comps.damodaran_fallback.call_count == 1
        assert (first_cached, second_cached) == (False, True)
    finally:
        close_session(sid)


# ---------------------------------------------------------------------------
# Part 2 — tool layer writes through the injected session_id
# ---------------------------------------------------------------------------

def test_get_financials_tool_reports_external_then_cache():
    from backend.agent.tools.research import get_financials

    sid = _new_session()
    try:
        with patch("backend.agent.cache.financials.financials_service") as mock_fin:
            mock_fin.get_cached_financials.return_value = _mock_hf("AAPL", [2022, 2023, 2024])

            first = get_financials.invoke({"ticker": "AAPL", "span": 3, "session_id": sid})
            second = get_financials.invoke({"ticker": "AAPL", "span": 3, "session_id": sid})

        assert first["source"] == "external"
        assert second["source"] == "cache"

        # Verify data landed in DuckDB
        conn = open_connection(sid)
        conn.execute("SELECT COUNT(*) FROM financials WHERE ticker = 'AAPL'")
        assert conn.fetchone()[0] == 3
        conn.close()
    finally:
        close_session(sid)


def test_tool_content_serializes_models_and_dicts():
    assert '"source"' in tool_content({"source": "cache"})
    assert '"current_price"' in tool_content(_mock_md())


# ---------------------------------------------------------------------------
# Part 3 — state evolution: sequential and concurrent writes both persist
# ---------------------------------------------------------------------------

def test_sequential_writes_accumulate_in_db():
    """Simulate two sequential tools-node turns writing to the same session."""
    sid = _new_session()
    conn = open_connection(sid)
    try:
        FinancialsCache._store(conn, _mock_hf("AAPL", [2023, 2024]), span=2)
        MarketDataCache._store(conn, "MSFT", _mock_md(), include_rfr=True)

        conn.execute("SELECT COUNT(*) FROM financials WHERE ticker = 'AAPL'")
        assert conn.fetchone()[0] == 2

        conn.execute("SELECT COUNT(*) FROM market_data WHERE ticker = 'MSFT'")
        assert conn.fetchone()[0] == 1
    finally:
        conn.close()
        close_session(sid)


def test_concurrent_writes_both_survive():
    """Two async writes open separate connections to the same DB file and both succeed."""
    sid = _new_session()

    async def write_aapl():
        conn = open_connection(sid)
        FinancialsCache._store(conn, _mock_hf("AAPL", [2024]), span=1)
        conn.close()

    async def write_msft():
        conn = open_connection(sid)
        MarketDataCache._store(conn, "MSFT", _mock_md(), include_rfr=True)
        conn.close()

    try:
        asyncio.run(asyncio.gather(write_aapl(), write_msft()))

        conn = open_connection(sid)
        conn.execute("SELECT COUNT(*) FROM financials WHERE ticker = 'AAPL'")
        assert conn.fetchone()[0] == 1
        conn.execute("SELECT COUNT(*) FROM market_data WHERE ticker = 'MSFT'")
        assert conn.fetchone()[0] == 1
        conn.close()
    finally:
        close_session(sid)


def test_wider_span_overwrites_existing_periods():
    """Storing 5 periods for a ticker that only had 2 replaces the rows via INSERT OR REPLACE."""
    sid = _new_session()
    conn = open_connection(sid)
    try:
        FinancialsCache._store(conn, _mock_hf("AAPL", [2023, 2024]), span=2)
        FinancialsCache._store(conn, _mock_hf("AAPL", [2020, 2021, 2022, 2023, 2024]), span=5)

        conn.execute("SELECT COUNT(DISTINCT fiscal_year) FROM financials WHERE ticker = 'AAPL'")
        assert conn.fetchone()[0] == 5
    finally:
        conn.close()
        close_session(sid)


def test_catalog_reflects_db_contents():
    sid = _new_session()
    conn = open_connection(sid)
    try:
        assert build_data_catalog(conn) == {"companies": [], "global": {"sector_data_years": []}}

        FinancialsCache._store(conn, _mock_hf("AAPL", [2023, 2024]), span=2)

        catalog = build_data_catalog(conn)
        assert len(catalog["companies"]) == 1
        entry = catalog["companies"][0]
        assert entry["ticker"] == "AAPL"
        assert entry["searched"]["financials"]["available"] is True
        assert set(entry["searched"]["financials"]["fiscal_years"]) == {"FY2023", "FY2024"}
        assert entry["calculated"] == {}

        # A calculated result appears in calculated on the next catalog build.
        fake_liquidity = MagicMock(return_value={"current_ratio": [1.5]})
        with patch.dict(RatiosCache._RATIO_FUNCS, {"liquidity": fake_liquidity}):
            RatiosCache.get_or_calculate(conn, "AAPL", 2, "liquidity")
        catalog = build_data_catalog(conn)
        assert "ratios" in catalog["companies"][0]["calculated"]
    finally:
        conn.close()
        close_session(sid)


def test_payload_contains_stored_data_for_response_node():
    sid = _new_session()
    conn = open_connection(sid)
    try:
        FinancialsCache._store(conn, _mock_hf("AAPL", [2023, 2024]), span=2)
        MarketDataCache._store(conn, "AAPL", _mock_md(), include_rfr=True)

        payload = build_data_payload(conn)
        assert "AAPL" in payload
        assert len(payload["AAPL"]["financials"]["periods"]) == 2
        assert payload["AAPL"]["market_data"]["current_price"] == 100.0
    finally:
        conn.close()
        close_session(sid)


def test_payload_empty_when_no_data():
    sid = _new_session()
    conn = open_connection(sid)
    try:
        assert build_data_payload(conn) == {}
    finally:
        conn.close()
        close_session(sid)


# ---------------------------------------------------------------------------
# Part 4 — tools_node: end-to-end orchestration through the node interface
# ---------------------------------------------------------------------------

from backend.agent.nodes.tools import tools_node


def _make_tools_state(tool_calls: list[dict], session_id: str = "") -> dict:
    """Minimal AgentState sufficient for tools_node to run."""
    return {
        "messages": [AIMessage(content="", tool_calls=tool_calls)],
        "context": "",
        "current_year": 2024,
        "available_tools": {},
        "session_id": session_id,
    }


def test_tools_node_single_call_populates_db():
    """A single get_financials call writes to DuckDB and updates data_catalog."""
    sid = _new_session()
    try:
        state = _make_tools_state(
            [{"name": "get_financials", "args": {"ticker": "AAPL", "span": 3}, "id": "tc_1"}],
            session_id=sid,
        )

        with patch("backend.agent.cache.financials.financials_service") as mock_fin:
            mock_fin.get_cached_financials.return_value = _mock_hf("AAPL", [2022, 2023, 2024])
            result = asyncio.run(tools_node(state))

        assert "data_catalog" in result
        assert "messages" in result
        # No data_cache in result — DuckDB is the source of truth now
        assert "data_cache" not in result

        # AAPL financials should be in DuckDB
        conn = open_connection(sid)
        conn.execute("SELECT COUNT(*) FROM financials WHERE ticker = 'AAPL'")
        assert conn.fetchone()[0] == 3
        conn.close()

        tickers = [e["ticker"] for e in result["data_catalog"]["companies"]]
        assert "AAPL" in tickers

        assert len(result["messages"]) == 1
        assert result["messages"][0].name == "get_financials"
        assert result["messages"][0].tool_call_id == "tc_1"
    finally:
        close_session(sid)


def test_tools_node_cache_hit_on_second_run():
    """When DuckDB already holds the data, the tool reports source=cache and makes no external call."""
    sid = _new_session()
    try:
        # Pre-load AAPL financials directly into the session's DuckDB
        conn = open_connection(sid)
        FinancialsCache._store(conn, _mock_hf("AAPL", [2022, 2023, 2024]), span=3)
        conn.close()

        state = _make_tools_state(
            [{"name": "get_financials", "args": {"ticker": "AAPL", "span": 3}, "id": "tc_2"}],
            session_id=sid,
        )

        with patch("backend.agent.cache.financials.financials_service") as mock_fin:
            mock_fin.get_cached_financials.return_value = _mock_hf("AAPL", [2022, 2023, 2024])
            result = asyncio.run(tools_node(state))
            mock_fin.get_cached_financials.assert_not_called()

        content = json.loads(result["messages"][0].content)
        assert content["source"] == "cache"
    finally:
        close_session(sid)


def test_tools_node_two_tickers_parallel_writes():
    """Two calls for different tickers run concurrently and both land in DuckDB."""
    sid = _new_session()
    try:
        state = _make_tools_state(
            [
                {"name": "get_financials", "args": {"ticker": "AAPL", "span": 3}, "id": "tc_aapl"},
                {"name": "get_financials", "args": {"ticker": "MSFT", "span": 3}, "id": "tc_msft"},
            ],
            session_id=sid,
        )

        with patch("backend.agent.cache.financials.financials_service") as mock_fin:
            mock_fin.get_cached_financials.side_effect = (
                lambda ticker, span, **_: _mock_hf(ticker, [2022, 2023, 2024])
            )
            result = asyncio.run(tools_node(state))

        # Both tickers must be in DuckDB
        conn = open_connection(sid)
        conn.execute("SELECT DISTINCT ticker FROM financials ORDER BY ticker")
        tickers_in_db = {row[0] for row in conn.fetchall()}
        conn.close()
        assert {"AAPL", "MSFT"}.issubset(tickers_in_db)

        assert len(result["messages"]) == 2
        call_ids = {msg.tool_call_id for msg in result["messages"]}
        assert call_ids == {"tc_aapl", "tc_msft"}
    finally:
        close_session(sid)


def test_tools_node_global_call_no_ticker():
    """get_sector_data has no ticker arg so it goes through the global-calls path."""
    sid = _new_session()
    try:
        state = _make_tools_state(
            [{"name": "get_sector_data", "args": {"year": 2024}, "id": "tc_sector"}],
            session_id=sid,
        )

        with patch("backend.agent.cache.sector_data.financials_service") as mock_sector:
            mock_sector.get_sector_data.return_value = _mock_sd()
            result = asyncio.run(tools_node(state))

        # Sector data should be in DuckDB
        conn = open_connection(sid)
        conn.execute("SELECT year FROM sector_data WHERE year = 2024")
        assert conn.fetchone() is not None
        conn.close()

        assert result["data_catalog"]["global"]["sector_data_years"] == [2024]
        assert len(result["messages"]) == 1
        assert result["messages"][0].tool_call_id == "tc_sector"
    finally:
        close_session(sid)


def test_tools_node_unknown_tool_returns_error_message():
    """An unrecognised tool name produces a ToolMessage with error JSON rather than raising."""
    sid = _new_session()
    try:
        state = _make_tools_state(
            [{"name": "nonexistent_tool", "args": {}, "id": "tc_bad"}],
            session_id=sid,
        )

        result = asyncio.run(tools_node(state))

        assert len(result["messages"]) == 1
        msg = result["messages"][0]
        assert msg.tool_call_id == "tc_bad"

        content = json.loads(msg.content)
        assert "error" in content
        assert "available_tools" in content
    finally:
        close_session(sid)
