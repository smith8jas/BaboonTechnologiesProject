"""LangChain tools exposed to the agent graph.

Layout:
    base.py         ToolSpec, phases, cache injection, logging helpers
    research.py     tools that pull external data (financials, market, sector, web)
    calculation.py  tools that derive data from cached inputs (growth, ratios, DCF, comps)
    registry.py     TOOL_SPECS registry — the single place to register a new tool
"""

from .base import PHASE_CALCULATION, PHASE_RESEARCH, ToolSpec, apply_tool_spec
from .registry import AVAILABLE_TOOLS, TOOL_SPECS, TOOLS_BY_NAME, serialize_tools, tools

__all__ = [
    "AVAILABLE_TOOLS",
    "PHASE_CALCULATION",
    "PHASE_RESEARCH",
    "TOOL_SPECS",
    "TOOLS_BY_NAME",
    "ToolSpec",
    "apply_tool_spec",
    "serialize_tools",
    "tools",
]
