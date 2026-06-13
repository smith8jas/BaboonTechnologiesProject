"""Tools node: executes planned tool calls and writes their results to the DuckDB session."""

import asyncio
import json
import logging
from typing import Any

from langchain_core.messages import ToolMessage

from ..cache import build_data_catalog, tool_content
from ..cache.session import open_connection
from ..constants import SCRAPE_TOOL_NAME
from ..messages import latest_tool_calls
from ..state import AgentState
from ..tools import TOOLS_BY_NAME

logger = logging.getLogger(__name__)


async def tools_node(state: AgentState):
    """Execute planned tool calls and update the data catalog in state."""
    logger.info("Tools Node Activated")

    #Creates a list of the tool calls that do not involve scraping
    #latest_tool_calls scans previous message for any tool_calls
    non_scrape_calls = [tc for tc in latest_tool_calls(state) if tc.get("name") != SCRAPE_TOOL_NAME]

    #Groups the tool calls by ticker
    grouped_calls = _group_calls_by_ticker(non_scrape_calls)
    logger.debug("Grouped calls: %s", grouped_calls)

    #Session ID ties all tool writes to this conversation's DuckDB file
    session_id = state.get("session_id") or ""

    #Sets an empty list to fill with ToolMessages
    messages: list[ToolMessage] = []

    #global_calls are tool calls that do not require a ticker
    global_calls = grouped_calls.pop(None, [])
    logger.debug("Global calls: %s", global_calls)

    # Global (no-ticker) calls run first — their results may feed into ticker-scoped calls.
    if global_calls:
        messages.extend(await _run_ticker_group(global_calls, session_id))

    # All per-ticker groups run concurrently; DuckDB serialises concurrent file writes.
    group_results = await asyncio.gather(
        *[_run_ticker_group(calls, session_id) for calls in grouped_calls.values()]
    )
    for group_messages in group_results:
        messages.extend(group_messages)

    # Build catalog from DuckDB now that all tools have written their data.
    conn = open_connection(session_id)
    try:
        catalog = build_data_catalog(conn)
    finally:
        conn.close()

    return {
        "messages": messages,
        "data_catalog": catalog,
    }


async def _run_ticker_group(
    calls: list[dict[str, Any]],
    session_id: str,
) -> list[ToolMessage]:
    """Run all calls for one ticker sequentially to avoid DuckDB write-write conflicts.

    Calls within the same ticker share primary-key rows in DuckDB (e.g. financials).
    DuckDB's serializable MVCC rejects concurrent writes to the same key even with
    INSERT OR REPLACE, so we serialize within a ticker while still running different
    ticker groups concurrently in the outer asyncio.gather.
    """
    #Empty list of messages for 1 ticker that is filled in sequentially by ticker
    messages = []
    for call in calls:
        messages.append(await _execute_tool_call(call, session_id))
    return messages


async def _execute_tool_call(
    call: dict[str, Any],
    session_id: str,
) -> ToolMessage:
    """Invoke one tool call and return its ToolMessage."""

    #Defines arguments (Ticker and Period), tool_call_id and tool by name to call
    name = call.get("name")
    args = dict(call.get("args") or {})
    tool_call_id = call.get("id") or ""
    tool = TOOLS_BY_NAME.get(name)

    #If the tool does not exist it throws an error and returns a ToolMessage with that error
    if tool is None:
        content = json.dumps({"error": f"Unknown tool: {name}", "available_tools": sorted(TOOLS_BY_NAME)})
        return ToolMessage(content=content, name=name, tool_call_id=tool_call_id)

    #Invokes the tool in a thread so it does not block the event loop; each tool manages its own DuckDB connection
    try:
        result = await asyncio.to_thread(tool.invoke, {**args, "session_id": session_id})
        content = tool_content(result)
        return ToolMessage(content=content, name=name, tool_call_id=tool_call_id)
    #Returns an error if a tool call fails
    except Exception as exc:
        content = f"Tool execution failed for {name}: {exc}"
        return ToolMessage(content=content, name=name, tool_call_id=tool_call_id)


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
