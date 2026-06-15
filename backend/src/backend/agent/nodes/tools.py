"""Tools node: executes planned tool calls and writes their results to the DuckDB session."""

import asyncio
import json
import logging
import time
from typing import Any

from langchain_core.messages import ToolMessage

from ..cache import build_data_catalog, tool_content
from ..cache.session import open_connection
from ..constants import SCRAPE_TOOL_NAME
from ..messages import latest_tool_calls
from ..state import AgentState
from ..tools import TOOLS_BY_NAME
from ..tools.base import PHASE_CALCULATION, PHASE_RESEARCH

logger = logging.getLogger(__name__)


async def tools_node(state: AgentState):
    """Execute planned tool calls in two sequential phases.

    Phase 1 — research: external fetches (EDGAR, Yahoo, FRED, Damodaran).
    Phase 2 — calculation: pure DuckDB reads; raises CacheMissError if Phase 1
    data is absent, surfacing planning errors instead of hiding them.
    """
    logger.info("Tools Node Activated")

    non_scrape_calls = [tc for tc in latest_tool_calls(state) if tc.get("name") != SCRAPE_TOOL_NAME]

    research_calls    = [tc for tc in non_scrape_calls if _get_phase(tc) == PHASE_RESEARCH]
    calculation_calls = [tc for tc in non_scrape_calls if _get_phase(tc) == PHASE_CALCULATION]

    session_id = state.get("session_id") or ""
    messages: list[ToolMessage] = []

    # Phase 1: research tools — run concurrently by ticker.
    if research_calls:
        t0 = time.perf_counter()
        messages.extend(await _run_phase(research_calls, session_id))
        logger.info("Research phase completed in %.2fs", time.perf_counter() - t0)

    # Phase 2: calculation tools — run concurrently by ticker, but only after
    # all research data is in DuckDB.
    if calculation_calls:
        t0 = time.perf_counter()
        messages.extend(await _run_phase(calculation_calls, session_id))
        logger.info("Calculation phase completed in %.2fs", time.perf_counter() - t0)

    conn = open_connection(session_id)
    try:
        catalog = build_data_catalog(conn)
    finally:
        conn.close()

    return {
        "messages": messages,
        "data_catalog": catalog,
    }


async def _run_phase(
    calls: list[dict[str, Any]],
    session_id: str,
) -> list[ToolMessage]:
    """Run a set of tool calls concurrently by ticker and return their messages."""
    grouped = _group_calls_by_ticker(calls)
    global_calls = grouped.pop(None, [])

    messages: list[ToolMessage] = []

    if global_calls:
        messages.extend(await _run_ticker_group(global_calls, session_id))

    group_results = await asyncio.gather(
        *[_run_ticker_group(ticker_calls, session_id) for ticker_calls in grouped.values()]
    )
    for group_messages in group_results:
        messages.extend(group_messages)

    return messages


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


def _get_phase(call: dict[str, Any]) -> str:
    """Return the phase tag from the tool's registry metadata, defaulting to research."""
    tool = TOOLS_BY_NAME.get(call.get("name", ""))
    if tool is None:
        return PHASE_RESEARCH
    return (getattr(tool, "metadata", None) or {}).get("agent", {}).get("phase", PHASE_RESEARCH)


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
