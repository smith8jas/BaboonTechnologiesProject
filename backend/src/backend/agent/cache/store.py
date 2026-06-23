"""The one shared primitive every research/calculation tool writes through.

research_messages and calculated_messages (AgentState fields) are plain lists
of dicts, deduped by an `identifier` tuple — e.g. ("financials", "AAPL") or
("ratios", "AAPL", "liquidity"). Lists are conversation-scoped (a few dozen
entries at most), so a linear scan is simpler than maintaining a dict index.

Every entry has the same shape:
    {"tool": str, "identifier": tuple, "ticker": str | None, "cycle": int,
     "last_updated": str, "data": dict, "data_source": str}

`data_source` names the real upstream provenance of `data` (e.g. "SEC EDGAR",
"Yahoo Finance", "Damodaran (NYU Stern)", "FRED") rather than the internal
tool/function name — response_node cites this verbatim instead of asking the
LLM to infer a source from the tool name.

`data` is exactly what the tool returns under its "data" key — the same
content shown to the LLM as ToolMessage content. There is no separate
payload-reconstruction step anywhere downstream.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Callable

# tools_node now runs every call in a phase concurrently via asyncio.to_thread, so two
# tool calls can genuinely execute on different OS threads at once. find-then-mutate
# below is not atomic on its own — this lock makes the scan+write a single step so
# concurrent upserts (e.g. two get_financials calls for one ticker with different
# span/fiscal_years, or two tickers needing the same damodaran_sector entry) can
# never produce a duplicate or a lost update. Held only across the in-memory list
# scan/mutation, never across the tool's actual fetch, so it costs nothing real.
_upsert_lock = threading.Lock()


def now() -> str:
    """UTC timestamp used for every entry's last_updated field."""
    return datetime.now(timezone.utc).isoformat()


def find(messages: list[dict[str, Any]], identifier: tuple) -> dict[str, Any] | None:
    """Return the entry with this identifier, or None.

    Identifiers are constructed as tuples, but the checkpointer serializes state
    between turns through a format with no tuple type — entries that survive a
    turn boundary come back with a list identifier. Compare both sides as tuples
    so a lookup never silently misses live cached data because of that round-trip.
    """
    target = tuple(identifier)
    for entry in messages:
        if tuple(entry["identifier"]) == target:
            return entry
    return None


def upsert(
    messages: list[dict[str, Any]],
    *,
    tool: str,
    identifier: tuple,
    ticker: str | None,
    cycle: int,
    data: dict[str, Any],
    data_source: str,
    merge: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Replace the entry with this identifier (merging if `merge` is given) or append a new one.

    This is the only place that scans/dedups a message list — every research
    and calculation tool calls it instead of reimplementing the scan.
    """
    with _upsert_lock:
        existing = find(messages, identifier)
        if existing is not None:
            existing["data"] = merge(existing["data"], data) if merge else data
            existing["cycle"] = cycle
            existing["last_updated"] = now()
            existing["data_source"] = data_source
            return existing

        entry = {
            "tool": tool,
            "identifier": identifier,
            "ticker": ticker,
            "cycle": cycle,
            "last_updated": now(),
            "data": data,
            "data_source": data_source,
        }
        messages.append(entry)
        return entry
