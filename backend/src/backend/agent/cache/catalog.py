"""Catalog and payload builders that summarize the DuckDB cache for model prompts."""

from __future__ import annotations

import duckdb

from .comparables import CompsCache
from .dcf import DCFCache
from .financials import FinancialsCache
from .growth import GrowthCache
from .market_data import MarketDataCache
from .ratios import RatiosCache
from .sector_data import SectorDataCache

# All per-ticker cache classes. Each must expose:
#   catalog_key      str  — key used in catalog and payload dicts
#   catalog_category str  — "searched" or "calculated" (for build_data_catalog)
#   table_name       str  — DuckDB table that holds this cache's rows
#
# Adding a new per-ticker cache: append its class here. Both build functions
# and _TICKER_UNION_SQL pick it up automatically.
COMPANY_TOOL_CACHES = [
    FinancialsCache,
    MarketDataCache,
    GrowthCache,
    RatiosCache,
    DCFCache,
    CompsCache,
]

# Built from COMPANY_TOOL_CACHES so new caches are included automatically.
# `companies` is prepended explicitly — it is written by FinancialsCache but
# is a metadata table, not a cache class of its own.
_TICKER_UNION_SQL = (
    "\n    UNION ".join(
        ["SELECT ticker FROM companies"]
        + [f"SELECT ticker FROM {cls.table_name}" for cls in COMPANY_TOOL_CACHES]
    )
    + "\n    ORDER BY ticker"
)


def build_data_catalog(conn: duckdb.DuckDBPyConnection) -> dict:
    """Build a compact availability summary for model prompts."""
    catalog: dict = {"companies": [], "global": {"sector_data_years": []}}

    conn.execute(_TICKER_UNION_SQL)
    tickers = [row[0] for row in conn.fetchall()]

    for ticker in tickers:
        conn.execute("SELECT name FROM companies WHERE ticker = ?", [ticker])
        name_row = conn.fetchone()
        entry: dict = {
            "ticker": ticker,
            "name": name_row[0] if name_row else None,
            "searched": {},
            "calculated": {},
        }

        for CacheClass in COMPANY_TOOL_CACHES:
            result = CacheClass.catalog_entry(conn, ticker)
            if result:
                entry[CacheClass.catalog_category][CacheClass.catalog_key] = result

        catalog["companies"].append(entry)

    catalog["global"]["sector_data_years"] = SectorDataCache.catalog_entry(conn)
    return catalog


def build_data_payload(conn: duckdb.DuckDBPyConnection) -> dict:
    """Build the detailed cached data payload used by response generation."""
    payload: dict = {}

    conn.execute(_TICKER_UNION_SQL)
    tickers = [row[0] for row in conn.fetchall()]

    for ticker in tickers:
        entry: dict = {}

        for CacheClass in COMPANY_TOOL_CACHES:
            result = CacheClass.payload_entry(conn, ticker)
            if result:
                entry[CacheClass.catalog_key] = result

        if entry:
            payload[ticker] = entry

    sd = SectorDataCache.payload_entry(conn)
    if sd:
        payload["sector_data"] = sd

    return payload
