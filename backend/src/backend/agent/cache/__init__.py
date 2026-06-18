"""Agent-local data store: in-state tool message lists plus the catalog builder.

Layout:
    base.py       CacheHelpers, tool_content, CacheMissError
    store.py      upsert / find / now — the shared primitive every tool writes through
    merge.py      merge_financials_data — period-union + coalesce merge for financials
    catalog.py    build_data_catalog / purge

There is no DuckDB and no per-tool cache class here anymore — research and
calculation tools (agent/tools/research.py, agent/tools/calculation.py) read
and write research_messages/calculated_messages (plain lists living in
AgentState) directly via upsert()/find(), using merge_financials_data where
a partial-overlap merge is needed. response_node reads those same lists
directly — there is no separate payload builder.
"""

from .base import CacheHelpers, CacheMissError, tool_content
from .catalog import CALCULATED_KEEP, FETCHED_KEEP, build_data_catalog, purge
from .merge import merge_financials_data
from .store import find, now, upsert

__all__ = [
    "CacheHelpers",
    "CacheMissError",
    "CALCULATED_KEEP",
    "FETCHED_KEEP",
    "build_data_catalog",
    "find",
    "merge_financials_data",
    "now",
    "purge",
    "tool_content",
    "upsert",
]
