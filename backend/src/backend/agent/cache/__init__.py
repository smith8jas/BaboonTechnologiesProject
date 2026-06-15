"""Agent-local data cache: one module per tool cache plus shared helpers.

Layout:
    schema.py       cache key constants and dependency labels
    base.py         CacheHelpers, serialization helpers
    session.py      DuckDB session lifecycle (create / open / close)
    financials.py   FinancialsCache      (financials + companies tables)
    market_data.py  MarketDataCache      (market_data table)
    sector_data.py  SectorDataCache      (sector_data table)
    growth.py       GrowthCache          (growth_rates table)
    ratios.py       RatiosCache          (ratios table)
    dcf.py          DCFCache             (dcf table)
    comparables.py  CompsCache           (comparables table)
    catalog.py      catalog/payload builders for prompts
"""

from .base import CacheHelpers, tool_content
from .catalog import COMPANY_TOOL_CACHES, build_data_catalog, build_data_payload
from .comparables import CompsCache
from .damodaran import DamodaranSectorCache
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
    "DamodaranSectorCache",
    "DCFCache",
    "FinancialsCache",
    "GrowthCache",
    "MarketDataCache",
    "RatiosCache",
    "SectorDataCache",
    "build_data_catalog",
    "build_data_payload",
    "tool_content",
]
