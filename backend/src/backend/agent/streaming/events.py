"""Translate LangGraph node state deltas into frontend progress events."""

import json

from ..constants import SCRAPE_TOOL_NAME
from ..tools import TOOLS_BY_NAME

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


def events_from_node_update(node_name: str, state_update: dict) -> list[dict]:
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
            events.append({"type": "thought", "content": "Recursion limit approaching — composing response with available data"})
        elif plan_status == "needs_tools":
            for msg in messages:
                tool_calls = getattr(msg, "tool_calls", None) or []
                if tool_calls:
                    events.extend(_status_events_from_tool_calls(tool_calls))
        elif plan_status == "needs_scrape":
            for msg in messages:
                tool_calls = getattr(msg, "tool_calls", None) or []
                if any(tc.get("name") == SCRAPE_TOOL_NAME for tc in tool_calls):
                    events.append({"type": "status", "text": GROUP_LABELS["web_scrape"]})
        elif plan_status == "needs_scrape_and_tools":
            for msg in messages:
                tool_calls = getattr(msg, "tool_calls", None) or []
                if tool_calls:
                    non_scrape = [tc for tc in tool_calls if tc.get("name") != SCRAPE_TOOL_NAME]
                    has_scrape = any(tc.get("name") == SCRAPE_TOOL_NAME for tc in tool_calls)
                    if non_scrape:
                        events.extend(_status_events_from_tool_calls(non_scrape))
                    if has_scrape:
                        events.append({"type": "status", "text": GROUP_LABELS["web_scrape"]})
        elif plan_status == "ready_to_respond":
            events.append({"type": "thought", "content": "Sufficient data gathered — composing response"})

    elif node_name == "tools":
        tool_names: list[str] = []
        for msg in messages:
            name = getattr(msg, "name", None) or ""
            if name:
                tool_names.append(name)
        if tool_names:
            events.extend(_status_events_from_tool_names(tool_names))

    elif node_name == "react_node":
        plan_status = state_update.get("plan_status", "")
        if plan_status == "needs_tools":
            for msg in messages:
                tool_calls = getattr(msg, "tool_calls", None) or []
                non_scrape = [tc for tc in tool_calls if tc.get("name") != SCRAPE_TOOL_NAME]
                if non_scrape:
                    events.extend(_status_events_from_tool_calls(non_scrape))
        elif plan_status == "needs_scrape":
            for msg in messages:
                tool_calls = getattr(msg, "tool_calls", None) or []
                if any(tc.get("name") == SCRAPE_TOOL_NAME for tc in tool_calls):
                    events.append({"type": "status", "text": GROUP_LABELS["web_scrape"]})
        elif plan_status == "needs_scrape_and_tools":
            for msg in messages:
                tool_calls = getattr(msg, "tool_calls", None) or []
                non_scrape = [tc for tc in tool_calls if tc.get("name") != SCRAPE_TOOL_NAME]
                has_scrape = any(tc.get("name") == SCRAPE_TOOL_NAME for tc in tool_calls)
                if non_scrape:
                    events.extend(_status_events_from_tool_calls(non_scrape))
                if has_scrape:
                    events.append({"type": "status", "text": GROUP_LABELS["web_scrape"]})
        elif plan_status == "ready_to_respond":
            events.append({"type": "thought", "content": "Analysis complete — composing response"})

    elif node_name == "scrape_node":
        scrape_msgs = [m for m in messages if getattr(m, "name", None) == SCRAPE_TOOL_NAME]
        if scrape_msgs:
            events.append({"type": "thought", "content": f"Web search completed ({len(scrape_msgs)} topic(s) scraped)"})

    elif node_name == "response_node":
        if messages:
            events.append({"type": "thought", "content": "Composing response"})

    elif node_name == "judge_node":
        forced = state_update.get("forced_response_due_to_recursion", False)
        if not forced and state_update.get("judge_verdict") == "revise":
            events.append({"type": "thought", "content": "Reviewing response — revising..."})
            events.append({"type": "clear"})

    return events


def _status_events_from_tool_calls(tool_calls: list[dict]) -> list[dict]:
    tool_names = [tc.get("name", "") for tc in tool_calls]
    return _status_events_from_tool_names(tool_names)


def _status_events_from_tool_names(tool_names: list[str]) -> list[dict]:
    groups = {
        ((getattr(TOOLS_BY_NAME.get(name), "metadata", None) or {}).get("agent", {}) or {}).get("group")
        for name in tool_names
    }
    return [
        {"type": "status", "text": GROUP_LABELS[group]}
        for group in _GROUP_PRIORITY
        if group in groups
    ]
