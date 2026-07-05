"""Unit tests for the react insight layer.

Covers:
- _insight_entries group resolution, blank filtering, and cycle tagging
- react_node returning tool_insights alongside its scheduling decision
- insight events emitted from react_node state deltas
- response node receiving accumulated insights in its runtime context
"""

import asyncio
from unittest.mock import patch

from backend.agent.llm import build_system_prompt
from backend.agent.nodes.react import ReactDecision, ToolInsight, _insight_entries, react_node
from backend.agent.streaming.events import events_from_node_update


# ---------------------------------------------------------------------------
# _insight_entries
# ---------------------------------------------------------------------------

def test_insight_entries_resolve_group_and_cycle():
    entries = _insight_entries(
        [ToolInsight(tool_name="get_financials", insight="Revenue is decelerating.")],
        cycle=2,
    )
    assert entries == [{
        "tool_name": "get_financials",
        "group": "financial_statement",
        "insight": "Revenue is decelerating.",
        "cycle": 2,
    }]


def test_insight_entries_unknown_tool_gets_no_group():
    entries = _insight_entries(
        [ToolInsight(tool_name="made_up_tool", insight="Something notable.")],
        cycle=1,
    )
    assert entries[0]["group"] is None
    assert entries[0]["insight"] == "Something notable."


def test_insight_entries_skip_blank_insights():
    entries = _insight_entries(
        [
            ToolInsight(tool_name="get_financials", insight="   "),
            ToolInsight(tool_name="get_market_data", insight="Beta is unusually high."),
        ],
        cycle=1,
    )
    assert len(entries) == 1
    assert entries[0]["tool_name"] == "get_market_data"


# ---------------------------------------------------------------------------
# react_node returns insights
# ---------------------------------------------------------------------------

def _react_state() -> dict:
    return {
        "context": "",
        "current_year": 2026,
        "available_tools": {},
        "dialogue": [],
        "messages": [],
        "react_iterations": 0,
        "judge_react_extensions": 0,
    }


def _run_react(decision: ReactDecision) -> dict:
    async def fake_structured(state, prompt, schema, node, messages=None, extra_context=None):
        return decision

    with patch("backend.agent.nodes.react.invoke_llm_structured", fake_structured):
        return asyncio.run(react_node(_react_state()))


def test_react_node_returns_insights_when_done():
    decision = ReactDecision(
        rationale="All data captured.",
        insights=[ToolInsight(tool_name="get_financials", insight="Margins stable across span.")],
        tool_calls=[],
    )
    result = _run_react(decision)
    assert result["plan_status"] == "ready_to_respond"
    assert result["tool_insights"][0]["insight"] == "Margins stable across span."
    assert result["tool_insights"][0]["cycle"] == 1


def test_react_node_returns_insights_alongside_tool_calls():
    decision = ReactDecision.model_validate({
        "rationale": "Need market data next.",
        "insights": [{"tool_name": "get_financials", "insight": "Debt grew faster than revenue."}],
        "tool_calls": [{"tool_name": "get_market_data", "args": {"ticker": "AAPL"}}],
    })
    result = _run_react(decision)
    assert result["plan_status"] == "needs_tools"
    assert result["tool_insights"][0]["tool_name"] == "get_financials"


def test_react_node_insights_default_empty():
    result = _run_react(ReactDecision(rationale="done", tool_calls=[]))
    assert result["tool_insights"] == []


# ---------------------------------------------------------------------------
# Streaming events
# ---------------------------------------------------------------------------

def test_react_update_emits_insight_events():
    update = {
        "plan_status": "ready_to_respond",
        "tool_insights": [
            {"tool_name": "get_financials", "group": "financial_statement",
             "insight": "FCF turned negative in FY2025.", "cycle": 3},
        ],
    }
    events = events_from_node_update("react_node", update)
    insight_events = [e for e in events if e["type"] == "insight"]
    assert insight_events == [{
        "type": "insight",
        "content": "FCF turned negative in FY2025.",
        "group": "financial_statement",
        "tool_name": "get_financials",
    }]
    # Scheduling events still emitted after insights
    assert any(e["type"] == "thought" for e in events)


def test_react_update_without_insights_emits_none():
    events = events_from_node_update("react_node", {"plan_status": "ready_to_respond"})
    assert not [e for e in events if e["type"] == "insight"]


# ---------------------------------------------------------------------------
# Response context
# ---------------------------------------------------------------------------

def test_response_context_includes_tool_insights():
    state = {
        "context": "",
        "current_year": 2026,
        "tool_insights": [
            {"tool_name": "get_financials", "group": "financial_statement",
             "insight": "Inventory build-up outpaces sales.", "cycle": 1},
        ],
    }
    with patch("backend.agent.llm.NODE_PROVIDERS", {"response": "openai"}):
        content = build_system_prompt(state, "respond", node="response")
    assert "tool_insights" in content
    assert "Inventory build-up outpaces sales." in content


def test_response_context_omits_empty_tool_insights():
    state = {"context": "", "current_year": 2026, "tool_insights": []}
    with patch("backend.agent.llm.NODE_PROVIDERS", {"response": "openai"}):
        content = build_system_prompt(state, "respond", node="response")
    assert "tool_insights" not in content
