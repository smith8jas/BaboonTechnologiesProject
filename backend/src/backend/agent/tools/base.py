"""Shared plumbing for agent tools: spec metadata and logging."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

PHASE_RESEARCH = "research"
PHASE_ASSUMPTIONS = "assumptions"
PHASE_CALCULATION = "calculation"

# Execution order across the tool-execution nodes: research (external I/O)
# runs in exec_research; assumptions then calculation (pure computation over
# gathered data) run in exec_calc. Later phases always see earlier phases'
# writes — within a node via local copies, across nodes via the state.
PHASE_ORDER: tuple[str, ...] = (PHASE_RESEARCH, PHASE_ASSUMPTIONS, PHASE_CALCULATION)


@dataclass(frozen=True)
class ToolSpec:
    tool: Any
    group: str
    route: str
    phase: str

    @property
    def name(self) -> str:
        return self.tool.name

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "group": self.group,
            "route": self.route,
            "phase": self.phase,
        }


def apply_tool_spec(spec: ToolSpec):
    metadata = dict(getattr(spec.tool, "metadata", None) or {})
    metadata["agent"] = spec.metadata
    spec.tool.metadata = metadata
    return spec.tool


def log_cache_status(tool_name: str, was_cached: bool, **kwargs) -> None:
    details = ", ".join(f"{key}={value}" for key, value in kwargs.items() if value is not None)
    source = "cache" if was_cached else "external"
    logger.info("%s: data from %s%s", tool_name, source, f" ({details})" if details else "")
