"""Unit tests for the insight layer.

Covers:
- insight_node: one entry per tool result, group/cycle/query_index tagging,
  empty-insight and failed-call skipping, empty-batch no-op
- react_node returning a pure scheduling decision (no insights)
- insight events emitted from insight_node state deltas
- response node receiving only the current query's insights and scrapes
- react node receiving the persistent plan rationale
"""

import asyncio
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from backend.agent.llm import build_system_prompt
from backend.agent.nodes.insight import InsightNote, insight_node
from backend.agent.nodes.react import ReactDecision, react_node
from backend.agent.streaming.events import events_from_node_update


# ---------------------------------------------------------------------------
# insight_node
# ---------------------------------------------------------------------------

def _insight_state(tool_messages: list[ToolMessage]) -> dict:
    return {
        "context": "",
        "current_year": 2026,
        "available_tools": {},
        "dialogue": [HumanMessage(content="How healthy are AAPL's margins?")],
        "messages": [
            AIMessage(content="Plan rationale.", tool_calls=[
                {"id": "1", "name": "get_financials", "args": {}, "type": "tool_call"},
            ]),
            *tool_messages,
        ],
        "tool_guidance": "Assess margin durability.",
        "react_iterations": 1,
        "query_count": 2,
    }


def _run_insight(state: dict, fake_invoke) -> dict:
    with patch("backend.agent.nodes.insight.invoke_llm_structured", fake_invoke):
        return asyncio.run(insight_node(state))


def test_insight_node_tags_group_cycle_and_query_index():
    state = _insight_state([
        ToolMessage(content='{"data": 1}', name="get_financials", tool_call_id="1"),
    ])

    async def fake(state, prompt, schema, node, messages=None, extra_context=None):
        assert node == "insight"
        assert extra_context["tool_name"] == "get_financials"
        assert extra_context["plan_rationale"] == "Assess margin durability."
        assert "margins" in extra_context["user_query"]
        return InsightNote(insight="Margins are compressing.")

    result = _run_insight(state, fake)
    assert result["tool_insights"] == [{
        "tool_name": "get_financials",
        "group": "financial_statement",
        "insight": "Margins are compressing.",
        "cycle": 2,
        "query_index": 2,
    }]


def test_insight_node_writes_one_entry_per_tool_message():
    state = _insight_state([
        ToolMessage(content='{"a": 1}', name="get_financials", tool_call_id="1"),
        ToolMessage(content='{"b": 2}', name="get_market_data", tool_call_id="2"),
    ])

    async def fake(state, prompt, schema, node, messages=None, extra_context=None):
        return InsightNote(insight=f"Note for {extra_context['tool_name']}.")

    result = _run_insight(state, fake)
    assert [e["tool_name"] for e in result["tool_insights"]] == [
        "get_financials", "get_market_data",
    ]


def test_insight_node_skips_empty_insights():
    state = _insight_state([
        ToolMessage(content='{"a": 1}', name="get_financials", tool_call_id="1"),
        ToolMessage(content='{"b": 2}', name="get_market_data", tool_call_id="2"),
    ])

    async def fake(state, prompt, schema, node, messages=None, extra_context=None):
        if extra_context["tool_name"] == "get_financials":
            return InsightNote(insight="   ")
        return InsightNote(insight="Beta is unusually high.")

    result = _run_insight(state, fake)
    assert len(result["tool_insights"]) == 1
    assert result["tool_insights"][0]["tool_name"] == "get_market_data"


def test_insight_node_skips_failed_calls():
    state = _insight_state([
        ToolMessage(content='{"a": 1}', name="get_financials", tool_call_id="1"),
    ])

    async def fake(state, prompt, schema, node, messages=None, extra_context=None):
        raise RuntimeError("provider down")

    assert _run_insight(state, fake) == {}


def test_insight_node_no_tool_messages_is_noop():
    state = _insight_state([])
    state["messages"] = []

    async def fake(*args, **kwargs):  # pragma: no cover - must not be called
        raise AssertionError("should not invoke LLM without tool messages")

    assert _run_insight(state, fake) == {}


# ---------------------------------------------------------------------------
# react_node is a pure scheduler
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
        "query_count": 2,
    }


def _run_react(decision: ReactDecision) -> dict:
    async def fake_structured(state, prompt, schema, node, messages=None, extra_context=None):
        return decision

    with patch("backend.agent.nodes.react.invoke_llm_structured", fake_structured):
        return asyncio.run(react_node(_react_state()))


def test_react_node_finishes_without_insights():
    result = _run_react(ReactDecision(rationale="All data captured.", tool_calls=[]))
    assert result["plan_status"] == "ready_to_respond"
    assert "tool_insights" not in result


def test_react_node_schedules_tools_without_insights():
    decision = ReactDecision.model_validate({
        "rationale": "Need market data next.",
        "tool_calls": [{"tool_name": "get_market_data", "args": {"ticker": "AAPL"}}],
    })
    result = _run_react(decision)
    assert result["plan_status"] == "needs_tools"
    assert "tool_insights" not in result


# ---------------------------------------------------------------------------
# Streaming events
# ---------------------------------------------------------------------------

def test_insight_update_emits_insight_events():
    update = {
        "tool_insights": [
            {"tool_name": "get_financials", "group": "financial_statement",
             "insight": "FCF turned negative in FY2025.", "cycle": 3, "query_index": 1},
        ],
    }
    events = events_from_node_update("insight_node", update)
    assert events == [{
        "type": "insight",
        "content": "FCF turned negative in FY2025.",
        "group": "financial_statement",
        "tool_name": "get_financials",
    }]


def test_react_update_emits_scheduling_events_only():
    events = events_from_node_update("react_node", {"plan_status": "ready_to_respond"})
    assert not [e for e in events if e["type"] == "insight"]
    assert any(e["type"] == "thought" for e in events)


# ---------------------------------------------------------------------------
# Response context: current-query scoping
# ---------------------------------------------------------------------------

def test_response_context_includes_current_query_insights_only():
    state = {
        "context": "",
        "current_year": 2026,
        "query_count": 2,
        "tool_insights": [
            {"tool_name": "get_financials", "group": "financial_statement",
             "insight": "Old-turn note about leverage.", "cycle": 1, "query_index": 1},
            {"tool_name": "get_financials", "group": "financial_statement",
             "insight": "Inventory build-up outpaces sales.", "cycle": 1, "query_index": 2},
        ],
    }
    with patch("backend.agent.llm.NODE_PROVIDERS", {"response": "openai"}):
        content = build_system_prompt(state, "respond", node="response")
    assert "tool_insights" in content
    assert "Inventory build-up outpaces sales." in content
    assert "Old-turn note about leverage." not in content


def test_response_context_omits_empty_tool_insights():
    state = {"context": "", "current_year": 2026, "tool_insights": []}
    with patch("backend.agent.llm.NODE_PROVIDERS", {"response": "openai"}):
        content = build_system_prompt(state, "respond", node="response")
    assert "tool_insights" not in content


def test_response_context_omits_insights_from_prior_queries_only():
    state = {
        "context": "",
        "current_year": 2026,
        "query_count": 3,
        "tool_insights": [
            {"tool_name": "get_financials", "group": "financial_statement",
             "insight": "Stale insight.", "cycle": 2, "query_index": 1},
        ],
    }
    with patch("backend.agent.llm.NODE_PROVIDERS", {"response": "openai"}):
        content = build_system_prompt(state, "respond", node="response")
    assert "tool_insights" not in content


def test_response_context_scopes_scrape_history_to_current_query():
    state = {
        "context": "",
        "current_year": 2026,
        "query_count": 2,
        "scrape_history": [
            {"query": "old search", "query_index": 1, "url": "http://a",
             "title": "Old scrape", "snippet": "stale", "confidence": 0.9, "source_type": "news"},
            {"query": "new search", "query_index": 2, "url": "http://b",
             "title": "Fresh scrape", "snippet": "current", "confidence": 0.9, "source_type": "news"},
        ],
    }
    with patch("backend.agent.llm.NODE_PROVIDERS", {"response": "openai"}):
        content = build_system_prompt(state, "respond", node="response")
    assert "Fresh scrape" in content
    assert "Old scrape" not in content


def test_react_context_keeps_cross_turn_scrape_history():
    state = {
        "context": "",
        "current_year": 2026,
        "available_tools": {},
        "query_count": 2,
        "scrape_history": [
            {"query": "old search", "query_index": 1, "url": "http://a",
             "title": "Old scrape", "snippet": "stale", "confidence": 0.9, "source_type": "news"},
        ],
    }
    with patch("backend.agent.llm.NODE_PROVIDERS", {"react": "openai"}):
        content = build_system_prompt(state, "react", node="react")
    assert "Old scrape" in content


# ---------------------------------------------------------------------------
# React context: plan rationale persistence
# ---------------------------------------------------------------------------

def test_react_context_includes_plan_rationale():
    state = {
        "context": "",
        "current_year": 2026,
        "available_tools": {},
        "tool_guidance": "Assess margin durability across the 5-year span.",
    }
    with patch("backend.agent.llm.NODE_PROVIDERS", {"react": "openai"}):
        content = build_system_prompt(state, "react", node="react")
    assert "plan_rationale" in content
    assert "Assess margin durability across the 5-year span." in content


def test_react_context_omits_missing_plan_rationale():
    state = {"context": "", "current_year": 2026, "available_tools": {}}
    with patch("backend.agent.llm.NODE_PROVIDERS", {"react": "openai"}):
        content = build_system_prompt(state, "react", node="react")
    assert "plan_rationale" not in content
