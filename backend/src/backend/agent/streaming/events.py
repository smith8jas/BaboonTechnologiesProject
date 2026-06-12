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
                scrape_calls = [tc for tc in tool_calls if tc.get("name") == SCRAPE_TOOL_NAME]
                if scrape_calls:
                    events.append({"type": "status", "text": GROUP_LABELS["web_scrape"]})
                    topics = [tc.get("args", {}).get("topic", "") for tc in scrape_calls if tc.get("args", {}).get("topic")]
                    desc = f"Web search queued: {', '.join(topics)}" if topics else "Web search queued"
                    events.append({"type": "thought", "content": desc})
        elif plan_status == "needs_scrape_and_tools":
            for msg in messages:
                tool_calls = getattr(msg, "tool_calls", None) or []
                if tool_calls:
                    non_scrape = [tc for tc in tool_calls if tc.get("name") != SCRAPE_TOOL_NAME]
                    scrape_calls = [tc for tc in tool_calls if tc.get("name") == SCRAPE_TOOL_NAME]
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
                non_scrape = [tc for tc in tool_calls if tc.get("name") != SCRAPE_TOOL_NAME]
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
                scrape_calls = [tc for tc in tool_calls if tc.get("name") == SCRAPE_TOOL_NAME]
                if scrape_calls:
                    events.append({"type": "status", "text": GROUP_LABELS["web_scrape"]})
                    topics = [tc.get("args", {}).get("topic", "") for tc in scrape_calls if tc.get("args", {}).get("topic")]
                    desc = (f"Searching for more context (pass {react_itr}): {', '.join(topics)}" if topics
                            else f"Web search queued (pass {react_itr})")
                    events.append({"type": "thought", "content": desc})
        elif plan_status == "needs_scrape_and_tools":
            for msg in messages:
                tool_calls = getattr(msg, "tool_calls", None) or []
                non_scrape = [tc for tc in tool_calls if tc.get("name") != SCRAPE_TOOL_NAME]
                scrape_calls = [tc for tc in tool_calls if tc.get("name") == SCRAPE_TOOL_NAME]
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
        scrape_msgs = [m for m in messages if getattr(m, "name", None) == SCRAPE_TOOL_NAME]
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
        ((getattr(TOOLS_BY_NAME.get(name), "metadata", None) or {}).get("agent", {}) or {}).get("group")
        for name in tool_names
    }
    return [
        {"type": "status", "text": GROUP_LABELS[group]}
        for group in _GROUP_PRIORITY
        if group in groups
    ]
