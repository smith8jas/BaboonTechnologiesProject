"""Tools node: executes planned tool calls and writes their results into AgentState."""

import asyncio
import json
import logging
import time
from typing import Any

from langchain_core.messages import ToolMessage

from ..cache import build_data_catalog, tool_content
from ..constants import SCRAPE_TOOL_NAME
from ..messages import latest_tool_calls
from ..state import AgentState
from ..tools import TOOLS_BY_NAME
from ..tools.base import PHASE_CALCULATION, PHASE_RESEARCH

logger = logging.getLogger(__name__)


async def tools_node(state: AgentState):
    """Execute planned tool calls in two phases, each fully concurrent internally.

    Phase 1 — research: external fetches (EDGAR, Yahoo, FRED, Damodaran), written into
    a local working copy of research_messages.
    Phase 2 — calculation: pure reads of that same local copy; raises CacheMissError if
    Phase 1 data is absent, surfacing planning errors instead of hiding them. Writes into
    a local working copy of calculated_messages.

    Phase 2 only starts once phase 1 is fully awaited, so it always sees phase 1's writes
    from this same call. Within a phase, every call runs concurrently regardless of ticker —
    cache/store.py's upsert lock makes the underlying list mutation safe even when two calls
    write the same identifier at once.

    Both local copies are seeded from state and returned as this node's state delta.
    """
    logger.info("Tools Node Activated")

    non_scrape_calls = [tc for tc in latest_tool_calls(state) if tc.get("name") != SCRAPE_TOOL_NAME]

    research_calls    = [tc for tc in non_scrape_calls if _get_phase(tc) == PHASE_RESEARCH]
    calculation_calls = [tc for tc in non_scrape_calls if _get_phase(tc) == PHASE_CALCULATION]

    research_local = list(state.get("research_messages", []))
    calculated_local = list(state.get("calculated_messages", []))
    cycle = state.get("query_count", 0)
    messages: list[ToolMessage] = []

    if research_calls:
        t0 = time.perf_counter()
        messages.extend(await _run_phase(research_calls, research_local, calculated_local, cycle))
        logger.info("Research phase completed in %.2fs", time.perf_counter() - t0)

    if calculation_calls:
        t0 = time.perf_counter()
        messages.extend(await _run_phase(calculation_calls, research_local, calculated_local, cycle))
        logger.info("Calculation phase completed in %.2fs", time.perf_counter() - t0)

    catalog = build_data_catalog(research_local, calculated_local)

    return {
        "messages": messages,
        "data_catalog": catalog,
        "research_messages": research_local,
        "calculated_messages": calculated_local,
    }


async def _run_phase(
    calls: list[dict[str, Any]],
    research_local: list[dict],
    calculated_local: list[dict],
    cycle: int,
) -> list[ToolMessage]:
    """Run every call in this phase concurrently and return their messages."""
    return list(
        await asyncio.gather(
            *[_execute_tool_call(call, research_local, calculated_local, cycle) for call in calls]
        )
    )


async def _execute_tool_call(
    call: dict[str, Any],
    research_local: list[dict],
    calculated_local: list[dict],
    cycle: int,
) -> ToolMessage:
    """Invoke one tool call and return its ToolMessage."""

    name = call.get("name")
    args = dict(call.get("args") or {})
    tool_call_id = call.get("id") or ""
    tool = TOOLS_BY_NAME.get(name)

    if tool is None:
        content = json.dumps({"error": f"Unknown tool: {name}", "available_tools": sorted(TOOLS_BY_NAME)})
        return ToolMessage(content=content, name=name, tool_call_id=tool_call_id)

    injected: dict[str, Any] = {"research_messages": research_local, "cycle": cycle}
    if _get_phase(call) == PHASE_CALCULATION:
        injected["calculated_messages"] = calculated_local

    try:
        result = await asyncio.to_thread(tool.invoke, {**args, **injected})
        content = tool_content(result)
        return ToolMessage(content=content, name=name, tool_call_id=tool_call_id)
    except Exception as exc:
        content = f"Tool execution failed for {name}: {exc}"
        return ToolMessage(content=content, name=name, tool_call_id=tool_call_id)


def _get_phase(call: dict[str, Any]) -> str:
    """Return the phase tag from the tool's registry metadata, defaulting to research."""
    tool = TOOLS_BY_NAME.get(call.get("name", ""))
    if tool is None:
        return PHASE_RESEARCH
    return (getattr(tool, "metadata", None) or {}).get("agent", {}).get("phase", PHASE_RESEARCH)
