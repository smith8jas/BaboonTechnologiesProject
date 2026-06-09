"""Streaming interfaces for the LangGraph agent."""

import asyncio
import json
import logging

from .graph import (
    DEFAULT_RECURSION_LIMIT,
    _SCRAPE_TOOL_NAME,
    _TOOLS_BY_NAME,
    _agent_config,
    _initial_state,
    _set_turn_start_step,
)

logger = logging.getLogger(__name__)

GROUP_LABELS: dict[str, str] = {
    "financial_statement": "Fetching financial statements...",
    "market_data": "Fetching market data...",
    "sector_data": "Fetching sector data...",
    "growth_rate": "Calculating growth rates...",
    "ratio": "Calculating ratios...",
    "dcf": "Running DCF valuation...",
    "web_scrape": "Searching the web...",
}

_GROUP_PRIORITY: list[str] = [
    "financial_statement",
    "market_data",
    "sector_data",
    "growth_rate",
    "ratio",
    "dcf",
    "web_scrape",
]


def activate_agent_stream(
    user_input,
    agent,
    *,
    thread_id: str,
    recursion_limit: int = DEFAULT_RECURSION_LIMIT,
):
    """Synchronous generator wrapper around the async streaming interface."""
    chunks = asyncio.run(
        _collect_agent_stream(
            user_input,
            agent,
            thread_id=thread_id,
            recursion_limit=recursion_limit,
        )
    )
    yield from chunks


async def _collect_agent_stream(
    user_input,
    agent,
    *,
    thread_id: str,
    recursion_limit: int = DEFAULT_RECURSION_LIMIT,
) -> list[str]:
    """Collect streamed chunks into a list for the synchronous wrapper."""
    chunks = []
    async for chunk in activate_agent_stream_async(
        user_input,
        agent,
        thread_id=thread_id,
        recursion_limit=recursion_limit,
    ):
        chunks.append(chunk)
    return chunks


async def activate_agent_stream_async(
    user_input,
    agent,
    *,
    thread_id: str,
    recursion_limit: int = DEFAULT_RECURSION_LIMIT,
):
    """Stream the final assistant response from the agent graph asynchronously."""
    config = _agent_config(thread_id, recursion_limit)
    previous_state = await agent.aget_state(config)
    _set_turn_start_step(config, previous_state)
    emitted_response_tokens = False

    async for token, metadata in agent.astream(_initial_state(user_input), config=config, stream_mode="messages"):
        if metadata.get("langgraph_node") != "response_node":
            continue

        content = getattr(token, "content", "")
        if not content:
            continue

        emitted_response_tokens = True
        yield content

    if emitted_response_tokens:
        return

    result = (await agent.aget_state(config)).values
    final_message = result.get("messages", [])[-1] if result.get("messages") else None
    fallback = getattr(final_message, "content", "")
    if fallback:
        yield fallback


async def activate_agent_stream_events_async(
    user_input,
    agent,
    *,
    thread_id: str,
    recursion_limit: int = DEFAULT_RECURSION_LIMIT,
):
    """Yield structured progress events plus token-by-token response deltas.

    Event shapes:
      {"type": "thought", "content": "<human-readable step description>"}
      {"type": "status",  "text":    "<short progress label>"}
      {"type": "delta",   "content": "<response text>"}
    """
    config = _agent_config(thread_id, recursion_limit)
    previous_state = await agent.aget_state(config)
    _set_turn_start_step(config, previous_state)
    emitted_response_tokens = False
    emitted_delta = False
    emitted_status_texts: set[str] = set()

    async for mode, data in agent.astream(
        _initial_state(user_input),
        config=config,
        stream_mode=["updates", "messages"],
    ):
        if mode == "updates":
            for node_name, state_update in data.items():
                for event in _events_from_node_update(node_name, state_update):
                    if event["type"] == "status":
                        text = event.get("text", "")
                        if text in emitted_status_texts:
                            continue
                        emitted_status_texts.add(text)
                    if event["type"] == "delta":
                        emitted_delta = True
                    yield event
            continue

        token, metadata = data
        if metadata.get("langgraph_node") != "response_node":
            continue

        content = getattr(token, "content", "")
        if not content:
            continue

        if not emitted_response_tokens:
            yield {"type": "status", "text": "Almost ready..."}
            emitted_response_tokens = True

        emitted_delta = True
        yield {"type": "delta", "content": content}

    if emitted_delta:
        return

    result = (await agent.aget_state(config)).values
    final_message = result.get("messages", [])[-1] if result.get("messages") else None
    fallback = getattr(final_message, "content", "")
    if fallback:
        yield {"type": "delta", "content": fallback}


def _events_from_node_update(node_name: str, state_update: dict) -> list[dict]:
    """Translate a LangGraph node state delta into frontend event dicts."""
    events: list[dict] = []
    messages = state_update.get("messages", [])

    if node_name == "router":
        route = state_update.get("router_route", "end")
        if route == "plan_node":
            events.append({"type": "thought", "content": "Identified as a financial analysis request"})
        else:
            for msg in messages:
                content = getattr(msg, "content", "")
                if content:
                    events.append({"type": "delta", "content": content})

    elif node_name == "plan_node":
        forced = state_update.get("forced_response_due_to_recursion", False)
        plan_status = state_update.get("plan_status", "")
        if forced:
            events.append({"type": "thought", "content": "Recursion limit approaching - composing response with available data"})
        elif plan_status == "needs_tools":
            for msg in messages:
                tool_calls = getattr(msg, "tool_calls", None) or []
                if tool_calls:
                    events.extend(_status_events_from_tool_calls(tool_calls))
                    descs = [
                        "{name}({args})".format(
                            name=tc.get("name", ""),
                            args=", ".join(
                                f"{k}={v}" for k, v in (tc.get("args") or {}).items()
                            ),
                        )
                        for tc in tool_calls
                    ]
                    events.append({"type": "thought", "content": f"(Deep_plan_active) Requesting: {', '.join(descs)}"})
        elif plan_status == "needs_scrape":
            for msg in messages:
                tool_calls = getattr(msg, "tool_calls", None) or []
                scrape_calls = [tc for tc in tool_calls if tc.get("name") == _SCRAPE_TOOL_NAME]
                if scrape_calls:
                    events.append({"type": "status", "text": GROUP_LABELS["web_scrape"]})
                    topics = [tc.get("args", {}).get("topic", "") for tc in scrape_calls if tc.get("args", {}).get("topic")]
                    desc = f"Web search queued: {', '.join(topics)}" if topics else "Web search queued"
                    events.append({"type": "thought", "content": desc})
        elif plan_status == "needs_scrape_and_tools":
            for msg in messages:
                tool_calls = getattr(msg, "tool_calls", None) or []
                if tool_calls:
                    non_scrape = [tc for tc in tool_calls if tc.get("name") != _SCRAPE_TOOL_NAME]
                    scrape_calls = [tc for tc in tool_calls if tc.get("name") == _SCRAPE_TOOL_NAME]
                    if non_scrape:
                        events.extend(_status_events_from_tool_calls(non_scrape))
                        descs = [
                            "{name}({args})".format(
                                name=tc.get("name", ""),
                                args=", ".join(
                                    f"{k}={v}" for k, v in (tc.get("args") or {}).items()
                                ),
                            )
                            for tc in non_scrape
                        ]
                        events.append({"type": "thought", "content": f"(Deep_plan_active) Requesting: {', '.join(descs)}"})
                    if scrape_calls:
                        events.append({"type": "status", "text": GROUP_LABELS["web_scrape"]})
                        topics = [tc.get("args", {}).get("topic", "") for tc in scrape_calls if tc.get("args", {}).get("topic")]
                        desc = f"Web search queued: {', '.join(topics)}" if topics else "Web search queued"
                        events.append({"type": "thought", "content": desc})
        elif plan_status == "ready_to_respond":
            events.append({"type": "thought", "content": "Sufficient data gathered - composing response"})

    elif node_name == "tools":
        retrieved: list[str] = []
        tool_names: list[str] = []
        for msg in messages:
            name = getattr(msg, "name", None) or ""
            if not name:
                continue
            tool_names.append(name)
            source = ""
            try:
                data = json.loads(getattr(msg, "content", "{}") or "{}")
                source = data.get("source", "")
            except Exception:
                pass
            retrieved.append(f"{name} [{source}]" if source else name)
        if retrieved:
            events.extend(_status_events_from_tool_names(tool_names))
            events.append({"type": "thought", "content": f"Retrieved: {', '.join(retrieved)}"})

    elif node_name == "react_node":
        plan_status = state_update.get("plan_status", "")
        react_itr = state_update.get("react_iterations", "?")

        if plan_status == "needs_tools":
            for msg in messages:
                tool_calls = getattr(msg, "tool_calls", None) or []
                non_scrape = [tc for tc in tool_calls if tc.get("name") != _SCRAPE_TOOL_NAME]
                if non_scrape:
                    events.extend(_status_events_from_tool_calls(non_scrape))
                    descs = [
                        "{name}({args})".format(
                            name=tc.get("name", ""),
                            args=", ".join(f"{k}={v}" for k, v in (tc.get("args") or {}).items()),
                        )
                        for tc in non_scrape
                    ]
                    events.append({"type": "thought", "content": f"Requesting additional data (pass {react_itr}): {', '.join(descs)}"})
        elif plan_status == "needs_scrape":
            for msg in messages:
                tool_calls = getattr(msg, "tool_calls", None) or []
                scrape_calls = [tc for tc in tool_calls if tc.get("name") == _SCRAPE_TOOL_NAME]
                if scrape_calls:
                    events.append({"type": "status", "text": GROUP_LABELS["web_scrape"]})
                    topics = [tc.get("args", {}).get("topic", "") for tc in scrape_calls if tc.get("args", {}).get("topic")]
                    desc = (f"Searching for more context (pass {react_itr}): {', '.join(topics)}" if topics
                            else f"Web search queued (pass {react_itr})")
                    events.append({"type": "thought", "content": desc})
        elif plan_status == "needs_scrape_and_tools":
            for msg in messages:
                tool_calls = getattr(msg, "tool_calls", None) or []
                non_scrape = [tc for tc in tool_calls if tc.get("name") != _SCRAPE_TOOL_NAME]
                scrape_calls = [tc for tc in tool_calls if tc.get("name") == _SCRAPE_TOOL_NAME]
                if non_scrape:
                    events.extend(_status_events_from_tool_calls(non_scrape))
                    descs = [
                        "{name}({args})".format(
                            name=tc.get("name", ""),
                            args=", ".join(f"{k}={v}" for k, v in (tc.get("args") or {}).items()),
                        )
                        for tc in non_scrape
                    ]
                    events.append({"type": "thought", "content": f"Requesting additional data (pass {react_itr}): {', '.join(descs)}"})
                if scrape_calls:
                    events.append({"type": "status", "text": GROUP_LABELS["web_scrape"]})
                    topics = [tc.get("args", {}).get("topic", "") for tc in scrape_calls if tc.get("args", {}).get("topic")]
                    desc = (f"Searching for more context (pass {react_itr}): {', '.join(topics)}" if topics
                            else f"Web search queued (pass {react_itr})")
                    events.append({"type": "thought", "content": desc})
        elif plan_status == "ready_to_respond":
            events.append({"type": "thought", "content": "Analysis complete — composing response"})

    elif node_name == "scrape_node":
        scrape_msgs = [m for m in messages if getattr(m, "name", None) == _SCRAPE_TOOL_NAME]
        if scrape_msgs:
            events.append({"type": "status", "text": "Searching the web..."})
            events.append({"type": "thought", "content": f"Web search completed ({len(scrape_msgs)} topic(s) scraped)"})

    elif node_name == "response_node":
        if messages:
            events.append({"type": "thought", "content": "Composing response"})

    return events


def _status_events_from_tool_calls(tool_calls: list[dict]) -> list[dict]:
    tool_names = [tc.get("name", "") for tc in tool_calls]
    return _status_events_from_tool_names(tool_names)


def _status_events_from_tool_names(tool_names: list[str]) -> list[dict]:
    groups = {
        ((getattr(_TOOLS_BY_NAME.get(name), "metadata", None) or {}).get("agent", {}) or {}).get("group")
        for name in tool_names
    }
    return [
        {"type": "status", "text": GROUP_LABELS[group]}
        for group in _GROUP_PRIORITY
        if group in groups
    ]
