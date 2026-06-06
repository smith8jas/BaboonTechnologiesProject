"""Unit tests for structured agent stream event sequencing."""
import asyncio
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, AIMessageChunk

from backend.Agent.graph import (
    GROUP_LABELS,
    activate_agent_stream_events_async,
)


def _plan_update(*tool_names: str) -> tuple:
    tool_calls = [
        {"name": name, "args": {}, "id": f"tc_{name}", "type": "tool_call"}
        for name in tool_names
    ]
    msg = AIMessage(content="", tool_calls=tool_calls)
    return ("updates", {"plan_node": {"plan_status": "needs_tools", "messages": [msg]}})


def _tools_update(*tool_names: str) -> tuple:
    messages = [
        MagicMock(name=name, content='{"source": "cache"}')
        for name in tool_names
    ]
    for message, name in zip(messages, tool_names, strict=True):
        message.name = name
    return ("updates", {"tools": {"messages": messages}})


def _response_token(content: str) -> tuple:
    return ("messages", (AIMessageChunk(content=content), {"langgraph_node": "response_node"}))


def _router_direct_answer(content: str) -> tuple:
    return ("updates", {"router": {"router_route": "end", "messages": [AIMessage(content=content)]}})


def _make_agent(stream_items: list, fallback_content: str = "") -> MagicMock:
    agent = MagicMock()

    async def astream(*_args, **_kwargs):
        for item in stream_items:
            yield item

    async def aget_state(*_args, **_kwargs):
        last_msg = AIMessage(content=fallback_content) if fallback_content else None
        state_values = {"messages": [last_msg]} if last_msg else {"messages": []}
        return MagicMock(values=state_values, metadata={"step": -1})

    agent.astream = astream
    agent.aget_state = aget_state
    return agent


def _events(stream_items: list, fallback_content: str = "") -> list[dict]:
    async def collect():
        agent = _make_agent(stream_items, fallback_content)
        return [
            event
            async for event in activate_agent_stream_events_async(
                "analyze apple",
                agent,
                thread_id="t1",
            )
        ]

    return asyncio.run(collect())


def test_stream_emits_status_thoughts_and_token_deltas():
    events = _events(
        [
            _plan_update("get_financials", "get_market_data"),
            _tools_update("get_financials"),
            ("updates", {"response_node": {"messages": [AIMessage(content="full answer ignored")]}}),
            _response_token("Here is"),
            _response_token(" the answer."),
        ]
    )

    status_texts = [event["text"] for event in events if event["type"] == "status"]
    thought_texts = [event["content"] for event in events if event["type"] == "thought"]
    delta_texts = [event["content"] for event in events if event["type"] == "delta"]

    assert GROUP_LABELS["financial_statement"] in status_texts
    assert GROUP_LABELS["market_data"] in status_texts
    assert "Almost ready..." in status_texts
    assert any(text.startswith("Requesting:") for text in thought_texts)
    assert any(text.startswith("Retrieved:") for text in thought_texts)
    assert "Composing response" in thought_texts
    assert delta_texts == ["Here is", " the answer."]


def test_status_labels_are_deduplicated_across_plan_and_tool_updates():
    events = _events(
        [
            _plan_update("get_liquidity_ratios"),
            _tools_update("get_profitability_ratios"),
            _response_token("done"),
        ]
    )

    ratio_statuses = [
        event for event in events if event.get("text") == GROUP_LABELS["ratio"]
    ]
    assert len(ratio_statuses) == 1


def test_direct_router_answer_does_not_emit_status():
    events = _events([_router_direct_answer("Hello. How can I help?")])

    assert all(event["type"] != "status" for event in events)
    assert events == [{"type": "delta", "content": "Hello. How can I help?"}]


def test_fallback_emits_delta_when_no_streamed_delta_exists():
    events = _events(
        [
            _plan_update("get_financials"),
        ],
        fallback_content="Final answer from state.",
    )

    delta_texts = [event["content"] for event in events if event["type"] == "delta"]
    assert delta_texts == ["Final answer from state."]
