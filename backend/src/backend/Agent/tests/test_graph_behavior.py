"""Unit tests for fragile graph behaviors.

Covers:
- RouterDecision structured model (no prose parsing)
- _route_after_router / _route_after_plan dispatch
- _should_force_response recursion guard
- merge_cache across tickers
- get_or_fetch_financials cache reuse
- fiscal_years arg does not collapse to span=2
- _has_fiscal_years year-aware coverage check
"""

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from backend.Agent.cache import (
    _has_fiscal_years,
    _financials_from_cache_by_years,
    empty_data_cache,
    get_or_fetch_financials,
)
from backend.Agent.graph import (
    DEFAULT_RECURSION_LIMIT,
    RouterDecision,
    _route_after_plan,
    _route_after_router,
    _should_force_response,
)
from backend.Agent.state import merge_cache


# ---------------------------------------------------------------------------
# RouterDecision — structured model, not prose
# ---------------------------------------------------------------------------

def test_router_decision_plan_node():
    d = RouterDecision(route="plan_node")
    assert d.route == "plan_node"
    assert d.answer is None


def test_router_decision_end_with_answer():
    d = RouterDecision(route="end", answer="Hello!")
    assert d.route == "end"
    assert d.answer == "Hello!"


def test_router_decision_rejects_unknown_route():
    with pytest.raises(Exception):
        RouterDecision(route="something_else")


# ---------------------------------------------------------------------------
# Routing helpers
# ---------------------------------------------------------------------------

def test_route_after_router_plan_node():
    assert _route_after_router({"router_route": "plan_node"}) == "plan_node"


def test_route_after_router_end():
    assert _route_after_router({"router_route": "end"}) == "end"


def test_route_after_router_defaults_to_end():
    assert _route_after_router({}) == "end"


def test_route_after_plan_needs_tools():
    assert _route_after_plan({"plan_status": "needs_tools"}) == "tools"


def test_route_after_plan_ready():
    assert _route_after_plan({"plan_status": "ready_to_respond"}) == "response_node"


def test_route_after_plan_defaults_to_response():
    assert _route_after_plan({}) == "response_node"


# ---------------------------------------------------------------------------
# Recursion guard per turn
# ---------------------------------------------------------------------------

def _make_config(current_step: int, turn_start_step: int, recursion_limit: int = DEFAULT_RECURSION_LIMIT) -> dict:
    return {
        "recursion_limit": recursion_limit,
        "metadata": {"langgraph_step": current_step},
        "configurable": {"turn_start_step": turn_start_step},
    }


def test_should_force_response_at_limit():
    # turn_step == recursion_limit - 2  →  force
    config = _make_config(current_step=11, turn_start_step=1, recursion_limit=12)
    assert _should_force_response(config) is True


def test_should_force_response_past_limit():
    config = _make_config(current_step=13, turn_start_step=1, recursion_limit=12)
    assert _should_force_response(config) is True


def test_should_not_force_response_well_within_limit():
    config = _make_config(current_step=4, turn_start_step=1, recursion_limit=12)
    assert _should_force_response(config) is False


def test_should_not_force_response_missing_step():
    config = {"recursion_limit": 12, "configurable": {"turn_start_step": 0}}
    assert _should_force_response(config) is False


# ---------------------------------------------------------------------------
# merge_cache across tickers
# ---------------------------------------------------------------------------

def test_merge_cache_combines_separate_tickers():
    left = {"companies": {"AAPL": {"value": 1}}, "global": {}}
    right = {"companies": {"MSFT": {"value": 2}}, "global": {}}
    merged = merge_cache(left, right)
    assert "AAPL" in merged["companies"]
    assert "MSFT" in merged["companies"]


def test_merge_cache_right_wins_on_conflict():
    left = {"companies": {"AAPL": {"value": 1}}, "global": {}}
    right = {"companies": {"AAPL": {"value": 99}}, "global": {}}
    merged = merge_cache(left, right)
    assert merged["companies"]["AAPL"]["value"] == 99


def test_merge_cache_empty_left():
    right = {"companies": {"TSLA": {"data": True}}, "global": {}}
    merged = merge_cache(None, right)
    assert "TSLA" in merged["companies"]


def test_merge_cache_empty_right():
    left = {"companies": {"TSLA": {"data": True}}, "global": {}}
    merged = merge_cache(left, None)
    assert "TSLA" in merged["companies"]


def test_merge_cache_does_not_mutate_inputs():
    left = {"companies": {"AAPL": {"v": 1}}, "global": {}}
    right = {"companies": {"MSFT": {"v": 2}}, "global": {}}
    merge_cache(left, right)
    assert "MSFT" not in left["companies"]


# ---------------------------------------------------------------------------
# _has_fiscal_years — year-aware coverage
# ---------------------------------------------------------------------------

def _cache_with_financials(ticker: str, fiscal_years: list[int]) -> dict[str, Any]:
    cache = empty_data_cache()
    periods = {str(y): {"fiscal_year": y, "period_end": f"{y}-12-31"} for y in fiscal_years}
    cache["companies"][ticker] = {
        "ticker": ticker,
        "name": None,
        "searched": {
            "financials": {
                "coverage": {"fiscal_years": fiscal_years, "max_span": len(fiscal_years)},
                "periods_by_fiscal_year": periods,
                "metadata": {},
            }
        },
        "calculated": {},
    }
    return cache


def test_has_fiscal_years_all_present():
    cache = _cache_with_financials("AAPL", [2020, 2021, 2022, 2023, 2024])
    assert _has_fiscal_years(cache, "AAPL", [2021, 2022]) is True


def test_has_fiscal_years_missing_year():
    cache = _cache_with_financials("AAPL", [2023, 2024])
    assert _has_fiscal_years(cache, "AAPL", [2021, 2022]) is False


def test_has_fiscal_years_no_financials():
    cache = empty_data_cache()
    assert _has_fiscal_years(cache, "AAPL", [2021]) is False


# ---------------------------------------------------------------------------
# get_or_fetch_financials — cache reuse and fiscal_years span
# ---------------------------------------------------------------------------

def _mock_hf(ticker: str, fiscal_years: list[int]):
    """Build a minimal HistoricalFinancials-like mock."""
    from datetime import date as _date

    periods = []
    for y in fiscal_years:
        p = MagicMock()
        p.fiscal_year = y
        p.period_end = _date(y, 12, 31)
        p.model_dump.return_value = {"fiscal_year": y, "period_end": f"{y}-12-31"}
        periods.append(p)

    hf = MagicMock()
    hf.ticker = ticker
    hf.periods = periods
    hf.metadata.model_dump.return_value = {"name": ticker}
    return hf


def test_get_or_fetch_financials_reuses_cache():
    cache = _cache_with_financials("AAPL", [2020, 2021, 2022, 2023, 2024])
    with patch("backend.Agent.cache.financials") as mock_fin:
        result, was_cached = get_or_fetch_financials(cache, "AAPL", span=5)
        mock_fin.get_cached_financials.assert_not_called()
    assert was_cached is True


def test_get_or_fetch_financials_fetches_on_cache_miss():
    cache = empty_data_cache()
    fake_hf = _mock_hf("AAPL", [2022, 2023, 2024])
    with patch("backend.Agent.cache.financials") as mock_fin:
        mock_fin.get_cached_financials.return_value = fake_hf
        result, was_cached = get_or_fetch_financials(cache, "AAPL", span=3)
        mock_fin.get_cached_financials.assert_called_once_with("AAPL", 3)
    assert was_cached is False


def test_fiscal_years_does_not_use_span_2():
    """Requesting [2021, 2022] must fetch with a span large enough to reach 2021, not span=2."""
    cache = empty_data_cache()
    fake_hf = _mock_hf("AAPL", list(range(2018, 2026)))
    with patch("backend.Agent.cache.financials") as mock_fin:
        mock_fin.get_cached_financials.return_value = fake_hf
        get_or_fetch_financials(cache, "AAPL", span=5, fiscal_years=[2021, 2022])
        called_span = mock_fin.get_cached_financials.call_args[0][1]
    assert called_span > 2, f"Expected span > 2 but got {called_span}"


def test_fiscal_years_cache_hit_does_not_call_external():
    cache = _cache_with_financials("AAPL", [2020, 2021, 2022, 2023, 2024])
    with patch("backend.Agent.cache.financials") as mock_fin:
        result, was_cached = get_or_fetch_financials(cache, "AAPL", fiscal_years=[2021, 2022])
        mock_fin.get_cached_financials.assert_not_called()
    assert was_cached is True
