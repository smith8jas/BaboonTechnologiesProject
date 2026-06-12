"""Tools node: executes planned tool calls and merges their cache updates."""

import asyncio
import json
import logging
from copy import deepcopy
from typing import Any

from langchain_core.messages import ToolMessage

from ..cache import build_data_catalog, state_cache, tool_content
from ..constants import SCRAPE_TOOL_NAME
from ..messages import latest_tool_calls
from ..state import AgentState, merge_cache
from ..tools import TOOLS_BY_NAME

logger = logging.getLogger(__name__)


async def tools_node(state: AgentState):
    """Execute planned tool calls and merge their cache updates into state."""
    logger.info("Tools Node Activated")
    tool_calls = [tc for tc in latest_tool_calls(state) if tc.get("name") != SCRAPE_TOOL_NAME]
    print(f"[TOOLS] Executing {len(tool_calls)} tool call(s)")
    grouped_calls = _group_calls_by_ticker(tool_calls)
    base_cache = state_cache(state)
    messages: list[ToolMessage] = []

    global_calls = grouped_calls.pop(None, [])
    if global_calls:
        global_result = await _run_ticker_group(None, global_calls, base_cache)
        messages.extend(global_result["messages"])
        base_cache = global_result["data_cache"]

    group_results = await asyncio.gather(
        *[
            _run_ticker_group(ticker, calls, base_cache)
            for ticker, calls in grouped_calls.items()
        ]
    )

    merged_cache = base_cache
    for result in group_results:
        messages.extend(result["messages"])
        merged_cache = merge_cache(merged_cache, result["data_cache"])

    return {
        "messages": messages,
        "data_cache": merged_cache,
        "data_catalog": build_data_catalog(merged_cache),
    }


async def _run_ticker_group(
    ticker: str | None,
    calls: list[dict[str, Any]],
    data_cache: dict[str, Any],
) -> dict[str, Any]:
    async def _run_one(call: dict[str, Any]) -> tuple[ToolMessage, dict[str, Any]]:
        cache = deepcopy(data_cache)
        name = call.get("name")
        args = dict(call.get("args") or {})
        tool_call_id = call.get("id") or ""
        tool = TOOLS_BY_NAME.get(name)
        if tool is None:
            content = json.dumps({"error": f"Unknown tool: {name}", "available_tools": sorted(TOOLS_BY_NAME)})
            return ToolMessage(content=content, name=name, tool_call_id=tool_call_id), cache
        try:
            result = await asyncio.to_thread(tool.invoke, {**args, "data_cache": cache})
            content = tool_content(result)
        except Exception as exc:
            content = f"Tool execution failed for {name}: {exc}"
        return ToolMessage(content=content, name=name, tool_call_id=tool_call_id), cache

    results = await asyncio.gather(*[_run_one(call) for call in calls])
    messages = [msg for msg, _ in results]
    merged_cache = data_cache
    for _, call_cache in results:
        merged_cache = merge_cache(merged_cache, call_cache)
    return {"messages": messages, "data_cache": merged_cache}


def _group_calls_by_ticker(tool_calls: list[dict[str, Any]]) -> dict[str | None, list[dict[str, Any]]]:
    grouped: dict[str | None, list[dict[str, Any]]] = {}
    for call in tool_calls:
        args = call.get("args") or {}
        ticker = args.get("ticker")
        key = str(ticker).strip().upper() if ticker else None
        grouped.setdefault(key, []).append(call)
    return grouped
