"""Agent-local data cache: one module per tool cache plus shared helpers.

Layout:
    schema.py       cache key constants and dependency labels
    base.py         empty skeletons, CacheHelpers, serialization helpers
    financials.py   FinancialsCache      (searched bucket)
    market_data.py  MarketDataCache      (searched bucket)
    sector_data.py  SectorDataCache      (global bucket)
    growth.py       GrowthCache          (calculated bucket)
    ratios.py       RatiosCache          (calculated bucket)
    dcf.py          DCFCache             (calculated bucket)
    comparables.py  CompsCache           (calculated bucket)
    catalog.py      registry + catalog/payload builders for prompts
"""

from .base import (
    CacheHelpers,
    empty_data_cache,
    empty_data_catalog,
    financials_coverage,
    fiscal_year_key,
    state_cache,
    tool_content,
)
from .catalog import COMPANY_TOOL_CACHES, build_data_catalog, build_data_payload
from .comparables import CompsCache
from .dcf import DCFCache
from .financials import FinancialsCache
from .growth import GrowthCache
from .market_data import MarketDataCache
from .ratios import RatiosCache
from .sector_data import SectorDataCache

__all__ = [
    "CacheHelpers",
    "COMPANY_TOOL_CACHES",
    "CompsCache",
    "DCFCache",
    "FinancialsCache",
    "GrowthCache",
    "MarketDataCache",
    "RatiosCache",
    "SectorDataCache",
    "build_data_catalog",
    "build_data_payload",
    "empty_data_cache",
    "empty_data_catalog",
    "financials_coverage",
    "fiscal_year_key",
    "state_cache",
    "tool_content",
]
