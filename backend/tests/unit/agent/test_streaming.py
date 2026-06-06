"""Unit tests for activate_agent_stream event sequencing."""
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk

from backend.agent.graph import GROUP_LABELS, activate_agent_stream


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _plan_update(*tool_names: str) -> tuple:
    """Simulate a plan_node update that needs tools."""
    tool_calls = [
        {"name": name, "args": {}, "id": f"tc_{name}", "type": "tool_call"}
        for name in tool_names
    ]
    msg = AIMessage(content="", tool_calls=tool_calls)
    return ("updates", {"plan_node": {"plan_status": "needs_tools", "messages": [msg]}})


def _response_token(content: str) -> tuple:
    return ("messages", (AIMessageChunk(content=content), {"langgraph_node": "response_node"}))


def _router_token(content: str) -> tuple:
    return ("messages", (AIMessageChunk(content=content), {"langgraph_node": "router"}))


def _make_agent(stream_items: list, fallback_content: str = "") -> MagicMock:
    agent = MagicMock()
    agent.stream.return_value = iter(stream_items)
    last_msg = AIMessage(content=fallback_content) if fallback_content else None
    state_values = {"messages": [last_msg]} if last_msg else {"messages": []}
    agent.get_state.return_value = MagicMock(values=state_values)
    return agent


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_dcf_event_sequence():
    """Multi-pass DCF run emits group labels in order, then Almost ready…, then tokens."""
    stream = [
        _plan_update("get_financials", "get_market_data", "get_sector_data"),
        _plan_update("get_income_statement_growth_rates", "get_balance_sheet_growth_rates"),
        _plan_update("get_liquidity_ratios", "get_profitability_ratios"),
        _plan_update("run_dcf_valuation"),
        _response_token("Here is the DCF analysis"),
        _response_token(" for Apple."),
    ]
    agent = _make_agent(stream)

    events = list(activate_agent_stream("run a dcf on apple", agent, thread_id="t1"))

    status_events = [e for e in events if e["type"] == "status"]
    token_events = [e for e in events if e["type"] == "token"]
    status_texts = [e["text"] for e in status_events]

    # All expected labels are present
    assert GROUP_LABELS["financial_statement"] in status_texts
    assert GROUP_LABELS["growth_rate"] in status_texts
    assert GROUP_LABELS["ratio"] in status_texts
    assert GROUP_LABELS["dcf"] in status_texts
    assert "Almost ready…" in status_texts

    # One status per planning pass: market_data and sector_data share pass 1 with
    # financial_statement and are suppressed (financial_statement has higher priority).
    assert GROUP_LABELS["market_data"] not in status_texts
    assert GROUP_LABELS["sector_data"] not in status_texts
    assert len(status_events) == 5  # 4 planning passes + "Almost ready…"

    # DCF label comes before "Almost ready…"
    assert status_texts.index(GROUP_LABELS["dcf"]) < status_texts.index("Almost ready…")

    # All status events precede all token events
    last_status_idx = max(events.index(e) for e in status_events)
    first_token_idx = min(events.index(e) for e in token_events)
    assert last_status_idx < first_token_idx

    # Deduplication: each label appears at most once
    assert len(status_texts) == len(set(status_texts))

    # Token content is correct
    assert token_events[0]["text"] == "Here is the DCF analysis"
    assert token_events[1]["text"] == " for Apple."


def test_greeting_no_status_lines():
    """A direct router reply (no planning) produces zero status events."""
    stream = [
        _router_token("Hello! How can I help?"),
    ]
    agent = _make_agent(stream, fallback_content="Hello! How can I help?")

    events = list(activate_agent_stream("hi", agent, thread_id="t2"))

    assert all(e["type"] != "status" for e in events), "Greetings must not emit status events"
    token_events = [e for e in events if e["type"] == "token"]
    assert len(token_events) >= 1


def test_deduplication_same_group_two_passes():
    """Two plan passes calling tools from the same group emit only one label."""
    stream = [
        _plan_update("get_liquidity_ratios"),
        _plan_update("get_profitability_ratios"),  # same "ratio" group
        _response_token("done"),
    ]
    agent = _make_agent(stream)

    events = list(activate_agent_stream("analyze ratios", agent, thread_id="t3"))
    ratio_statuses = [e for e in events if e.get("text") == GROUP_LABELS["ratio"]]
    assert len(ratio_statuses) == 1


def test_fallback_with_planning_adds_almost_ready():
    """If planning ran but response_node produced no streaming tokens, Almost ready… still appears before fallback."""
    stream = [
        _plan_update("get_financials"),
        # No response_node tokens — agent ends silently
    ]
    agent = _make_agent(stream, fallback_content="Final answer from state.")

    events = list(activate_agent_stream("check financials", agent, thread_id="t4"))

    status_texts = [e["text"] for e in events if e["type"] == "status"]
    token_texts = [e["text"] for e in events if e["type"] == "token"]

    assert "Almost ready…" in status_texts
    assert token_texts == ["Final answer from state."]
    # "Almost ready…" must come before the token
    almost_ready_idx = next(i for i, e in enumerate(events) if e.get("text") == "Almost ready…")
    token_idx = next(i for i, e in enumerate(events) if e["type"] == "token")
    assert almost_ready_idx < token_idx


def test_fallback_without_planning_no_almost_ready():
    """Router short-circuit with no tool planning: fallback token only, no Almost ready…."""
    stream = [
        _router_token(""),  # router produces no useful streaming content
    ]
    agent = _make_agent(stream, fallback_content="Direct answer.")

    events = list(activate_agent_stream("what is beta?", agent, thread_id="t5"))

    assert all(e.get("text") != "Almost ready…" for e in events)
    token_events = [e for e in events if e["type"] == "token"]
    assert token_events[0]["text"] == "Direct answer."
