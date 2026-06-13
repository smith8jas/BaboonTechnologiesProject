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

    #Creates a list of the tool calls that do not involve scraping
    non_scrape_calls = [tc for tc in latest_tool_calls(state) if tc.get("name") != SCRAPE_TOOL_NAME]

    #Groups the tool calls by ticker
    grouped_calls = _group_calls_by_ticker(non_scrape_calls)
    logger.debug("Grouped calls: %s", grouped_calls)

    #Obtains the current data cache (where financial data is stored in short memory) from state.
    base_cache = state_cache(state)

    #Sets an empty list to fill with ToolMessages
    messages: list[ToolMessage] = []

    #Removes tool calls that do not belong to a ticker from grouped_calls
    global_calls = grouped_calls.pop(None, [])
    logger.debug("Global calls: %s", global_calls)

    # Global (no-ticker) calls run first — their results may feed into ticker-scoped calls.
    if global_calls:
        global_result = await _run_ticker_group(global_calls, base_cache)
        messages.extend(global_result["messages"])
        base_cache = global_result["data_cache"]

    # All per-ticker groups run concurrently, each starting from the same base_cache snapshot.
    group_results = await asyncio.gather(
        *[_run_ticker_group(calls, base_cache) for calls in grouped_calls.values()]
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
    calls: list[dict[str, Any]],
    data_cache: dict[str, Any],
) -> dict[str, Any]:
    """Run all calls for one ticker concurrently, then fold their cache deltas together."""

    #Runs the tools asynchronically
    #results is a tuple with the ToolMessage and the updated cache for each tool call
    results = await asyncio.gather(*[_execute_tool_call(call, data_cache) for call in calls])

    messages = [msg for msg, _ in results]

    # Start from a clean copy so the returned dict is always self-contained.
    merged_cache = deepcopy(data_cache)
    for _, call_cache in results:
        merged_cache = merge_cache(merged_cache, call_cache)

    return {"messages": messages, "data_cache": merged_cache}


async def _execute_tool_call(
    call: dict[str, Any],
    data_cache: dict[str, Any],
) -> tuple[ToolMessage, dict[str, Any]]:
    """Invoke one tool call and return its ToolMessage paired with the updated cache snapshot."""

    #Defines arguments (Ticker and Period), tool_call_id and tool by name to call
    name = call.get("name")
    args = dict(call.get("args") or {})
    tool_call_id = call.get("id") or ""
    tool = TOOLS_BY_NAME.get(name)

    #If the tool does not exist it throws an error and returns a ToolMessage with that error
    if tool is None:
        content = json.dumps({"error": f"Unknown tool: {name}", "available_tools": sorted(TOOLS_BY_NAME)})
        return ToolMessage(content=content, name=name, tool_call_id=tool_call_id), deepcopy(data_cache)

    #Another copy of the cache in State to replace with new values
    # Each call gets its own deep copy so concurrent siblings don't share mutable state.
    cache = deepcopy(data_cache)

    #Invokes the tools asynchronically with defined arguments and the cache copy
    try:
        result = await asyncio.to_thread(tool.invoke, {**args, "data_cache": cache})
        content = tool_content(result)
        return ToolMessage(content=content, name=name, tool_call_id=tool_call_id), cache
    #Returns an error if a tool call fails
    except Exception as exc:
        content = f"Tool execution failed for {name}: {exc}"
        # Return a clean snapshot — cache may be partially mutated if the tool raised mid-write.
        return ToolMessage(content=content, name=name, tool_call_id=tool_call_id), deepcopy(data_cache)


def _group_calls_by_ticker(
    tool_calls: list[dict[str, Any]],
) -> dict[str | None, list[dict[str, Any]]]:
    """Bucket tool calls by ticker (None for calls with no ticker argument)."""

    #Empty dict with specific format
    grouped: dict[str | None, list[dict[str, Any]]] = {}

    #Goes over the tool calls
    for call in tool_calls:

        #Extracts the ticker from each tool call
        args = call.get("args") or {}
        ticker = args.get("ticker")

        #Makes the ticker all caps and removes space at the beginning and end of the tool call
        key = str(ticker).strip().upper() if ticker else None

        #Creates a dictionary of tickers, each with a list of tool calls and their arguments.
        grouped.setdefault(key, []).append(call)

    return grouped
