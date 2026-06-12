"""Shared plumbing for agent tools: spec metadata, cache injection, logging."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ..cache import empty_data_cache

logger = logging.getLogger(__name__)

PHASE_RESEARCH = "research"
PHASE_CALCULATION = "calculation"


@dataclass(frozen=True)
class ToolSpec:
    tool: Any
    group: str
    route: str
    capability: str
    phase: str

    @property
    def name(self) -> str:
        return self.tool.name

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "group": self.group,
            "route": self.route,
            "capability": self.capability,
            "phase": self.phase,
        }


def apply_tool_spec(spec: ToolSpec):
    metadata = dict(getattr(spec.tool, "metadata", None) or {})
    metadata["agent"] = spec.metadata
    spec.tool.metadata = metadata
    return spec.tool


def tool_cache(data_cache: dict | None) -> dict:
    return data_cache if data_cache is not None else empty_data_cache()


def log_cache_status(tool_name: str, was_cached: bool, **kwargs) -> None:
    details = ", ".join(f"{key}={value}" for key, value in kwargs.items() if value is not None)
    source = "cache" if was_cached else "external"
    logger.info("%s: data from %s%s", tool_name, source, f" ({details})" if details else "")
