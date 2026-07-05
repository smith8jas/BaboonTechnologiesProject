"""Tool-execution nodes: run planned tool calls and write results into AgentState.

Execution is split into two graph nodes built from the same phase runner:

    plan/react ──(Send ∥)──► scrape_node ─────┐
                        └───► exec_research ──┴──► exec_calc ──► react

- exec_research runs research-phase tools (external I/O: EDGAR, Yahoo, FRED,
  Damodaran) and is the single writer of research_messages.
- exec_calc runs assumptions- then calculation-phase tools (pure computation)
  and is the single writer of calculated_messages and data_catalog.

Both parallel branches (scrape_node, exec_research) are exactly one hop, so
they finish in the same superstep and exec_calc runs once with both writes
visible — assumptions-phase tools see this same cycle's scrape_history and
research results without a react iteration in between.

Promoting a phase to its own node later (e.g. an agent-based-modeling
assumptions node) is just another `run_tool_phases` instantiation wired into
the graph.
"""

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
from ..tools.base import PHASE_ASSUMPTIONS, PHASE_CALCULATION, PHASE_ORDER, PHASE_RESEARCH

logger = logging.getLogger(__name__)

# Phases whose tools also receive (and write) calculated_messages.
_CALCULATED_WRITER_PHASES = {PHASE_ASSUMPTIONS, PHASE_CALCULATION}


async def exec_research_node(state: AgentState):
    """Execute this batch's research-phase tool calls (external fetches)."""
    logger.info("Exec Research Node Activated")
    return await run_tool_phases(state, phases=(PHASE_RESEARCH,))


async def exec_calc_node(state: AgentState):
    """Execute this batch's assumptions- and calculation-phase tool calls.

    Runs after exec_research and scrape_node have written their deltas, so
    tools here read the full picture of the current cycle. As the single
    writer of data_catalog it always refreshes it — research/scrape activity
    earlier in this cycle must land in the catalog even when no
    assumptions/calculation tools ran.
    """
    logger.info("Exec Calc Node Activated")
    delta = await run_tool_phases(state, phases=(PHASE_ASSUMPTIONS, PHASE_CALCULATION))
    calculated = delta.get("calculated_messages", state.get("calculated_messages", []))
    delta["data_catalog"] = build_data_catalog(state.get("research_messages", []), calculated)
    return delta


async def run_tool_phases(state: AgentState, phases: tuple[str, ...]) -> dict:
    """Execute the current batch's tool calls for `phases`, in PHASE_ORDER.

    Each phase runs fully concurrently; a later phase only starts once the
    prior one is awaited, so it always sees its writes via the shared local
    copies. Local copies are seeded from state and returned as this node's
    delta — research_messages only when a research phase ran here,
    calculated_messages/data_catalog only when a calculated-writer phase ran.

    Scrape calls are the scrape_node's contract (see tools/research.py:
    scrape_web is a thin transition layer for non-graph callers) and are
    excluded here by a hard guard — inside the graph they never execute
    through the tool body.
    """
    non_scrape_calls = [tc for tc in latest_tool_calls(state) if tc.get("name") != SCRAPE_TOOL_NAME]
    ordered_phases = [p for p in PHASE_ORDER if p in phases]
    calls_by_phase = {
        phase: [tc for tc in non_scrape_calls if _get_phase(tc) == phase]
        for phase in ordered_phases
    }

    if not any(calls_by_phase.values()):
        return {}

    research_local = list(state.get("research_messages", []))
    calculated_local = list(state.get("calculated_messages", []))
    cycle = state.get("query_count", 0)
    messages: list[ToolMessage] = []

    for phase in ordered_phases:
        calls = calls_by_phase[phase]
        if not calls:
            continue
        t0 = time.perf_counter()
        messages.extend(
            await _run_phase(phase, calls, research_local, calculated_local, cycle)
        )
        logger.info("%s phase completed in %.2fs", phase.capitalize(), time.perf_counter() - t0)

    delta: dict[str, Any] = {"messages": messages}
    if calls_by_phase.get(PHASE_RESEARCH):
        delta["research_messages"] = research_local
    if any(calls_by_phase.get(p) for p in _CALCULATED_WRITER_PHASES):
        delta["calculated_messages"] = calculated_local
    return delta


async def _run_phase(
    phase: str,
    calls: list[dict[str, Any]],
    research_local: list[dict],
    calculated_local: list[dict],
    cycle: int,
) -> list[ToolMessage]:
    """Run every call in this phase concurrently and return their messages."""
    return list(
        await asyncio.gather(
            *[
                _execute_tool_call(phase, call, research_local, calculated_local, cycle)
                for call in calls
            ]
        )
    )


async def _execute_tool_call(
    phase: str,
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
    if phase in _CALCULATED_WRITER_PHASES:
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


async def tools_node(state: AgentState):
    """Single-node execution of every phase — kept for direct/legacy callers.

    The graph now routes through exec_research_node → exec_calc_node; this
    wrapper runs the same runner over all phases in one call and preserves the
    original full-delta contract (both channels plus a refreshed catalog).
    """
    logger.info("Tools Node Activated")
    delta = await run_tool_phases(state, phases=PHASE_ORDER)
    delta.setdefault("messages", [])
    delta.setdefault("research_messages", list(state.get("research_messages", [])))
    delta.setdefault("calculated_messages", list(state.get("calculated_messages", [])))
    delta["data_catalog"] = build_data_catalog(
        delta["research_messages"], delta["calculated_messages"]
    )
    return delta
