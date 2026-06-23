"""Unit tests for fragile graph behaviors.

Covers:
- RouterDecision structured model (no prose parsing)
- route_after_router / route_after_plan / route_after_react dispatch
- should_force_response recursion guard

Note: this file previously also covered an in-memory nested-dict cache
(`empty_data_cache`, `merge_cache`) and `FinancialsCache.get_or_fetch` against
a DuckDB connection — both predate the current research_messages/
calculated_messages design and no longer exist. Coverage for "is this fiscal
year already covered" now lives in test_cache_state_evolution.py, against
get_financials directly.
"""

import pytest

from backend.agent.constants import DEFAULT_RECURSION_LIMIT
from backend.agent.edges import route_after_plan, route_after_react, route_after_router
from backend.agent.llm import build_system_prompt
from backend.agent.nodes.router import RouterDecision
from backend.agent.prompts import response_prompt
from backend.agent.runtime import should_force_response


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
# Routing edges
# ---------------------------------------------------------------------------

def test_route_after_router_plan_node():
    assert route_after_router({"router_route": "plan_node"}) == "plan_node"


def test_route_after_router_end():
    assert route_after_router({"router_route": "end"}) == "end"


def test_route_after_router_defaults_to_end():
    assert route_after_router({}) == "end"


def test_route_after_plan_needs_tools():
    assert route_after_plan({"plan_status": "needs_tools"}) == "tools"


def test_route_after_plan_needs_scrape():
    assert route_after_plan({"plan_status": "needs_scrape"}) == "scrape_node"


def test_route_after_plan_scrape_and_tools_fans_out():
    result = route_after_plan({"plan_status": "needs_scrape_and_tools"})
    assert isinstance(result, list)
    assert {send.node for send in result} == {"scrape_node", "tools"}


def test_route_after_plan_ready():
    assert route_after_plan({"plan_status": "ready_to_respond"}) == "response_node"


def test_route_after_plan_defaults_to_response():
    assert route_after_plan({}) == "response_node"


def test_route_after_react_matches_plan_routing():
    for status, expected in [
        ("needs_tools", "tools"),
        ("needs_scrape", "scrape_node"),
        ("ready_to_respond", "response_node"),
    ]:
        assert route_after_react({"plan_status": status}) == expected


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
    assert should_force_response(config) is True


def test_should_force_response_past_limit():
    config = _make_config(current_step=13, turn_start_step=1, recursion_limit=12)
    assert should_force_response(config) is True


def test_should_not_force_response_well_within_limit():
    config = _make_config(current_step=4, turn_start_step=1, recursion_limit=12)
    assert should_force_response(config) is False


def test_should_not_force_response_missing_step():
    config = {"recursion_limit": 12, "configurable": {"turn_start_step": 0}}
    assert should_force_response(config) is False


# ---------------------------------------------------------------------------
# Judge context
# ---------------------------------------------------------------------------

def test_judge_receives_cached_data_catalog():
    state = {
        "context": "",
        "current_year": 2026,
        "data_catalog": {
            "companies": [
                {
                    "ticker": "TSLA",
                    "searched": {},
                    "calculated": {
                        "dcf": {
                            "default": {
                                "available": True,
                                "summary": "Run a full DCF valuation.",
                            }
                        }
                    },
                }
            ],
            "global": {"sector_data_years": [2026]},
        },
    }

    blocks = build_system_prompt(state, "judge instructions", node="judge")
    runtime_context = blocks[1]["text"]

    assert "cached_data_catalog" in runtime_context
    assert '"ticker": "TSLA"' in runtime_context
    assert '"dcf"' in runtime_context
    assert '"available": true' in runtime_context


def test_response_prompt_forbids_named_self_computed_ratios():
    assert "Named Ratio Boundary" in response_prompt
    assert "current ratio" in response_prompt
    assert "do not tag it [SUPPORTED]" in response_prompt
    assert "This exception does not permit named financial ratios" in response_prompt
