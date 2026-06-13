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

COMPANY_TOOL_CACHES = [
    FinancialsCache,
    MarketDataCache,
    GrowthCache,
    RatiosCache,
    DCFCache,
    CompsCache,
]

# All tables that carry a per-ticker column — UNION gives every ticker that has any data.
_TICKER_UNION_SQL = """
    SELECT ticker FROM companies
    UNION SELECT ticker FROM financials
    UNION SELECT ticker FROM market_data
    UNION SELECT ticker FROM growth_rates
    UNION SELECT ticker FROM ratios
    UNION SELECT ticker FROM dcf
    UNION SELECT ticker FROM comparables
    ORDER BY ticker
"""


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

        fin = FinancialsCache.catalog_entry(conn, ticker)
        if fin:
            entry["searched"]["financials"] = fin

        mkt = MarketDataCache.catalog_entry(conn, ticker)
        if mkt:
            entry["searched"]["market_data"] = mkt

        gro = GrowthCache.catalog_entry(conn, ticker)
        if gro:
            entry["calculated"]["growth"] = gro

        rat = RatiosCache.catalog_entry(conn, ticker)
        if rat:
            entry["calculated"]["ratios"] = rat

        dcf = DCFCache.catalog_entry(conn, ticker)
        if dcf:
            entry["calculated"]["dcf"] = dcf

        cmp = CompsCache.catalog_entry(conn, ticker)
        if cmp:
            entry["calculated"]["comparables"] = cmp

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

        fin = FinancialsCache.payload_entry(conn, ticker)
        if fin:
            entry["financials"] = fin

        mkt = MarketDataCache.payload_entry(conn, ticker)
        if mkt:
            entry["market_data"] = mkt

        gro = GrowthCache.payload_entry(conn, ticker)
        if gro:
            entry["growth"] = gro

        rat = RatiosCache.payload_entry(conn, ticker)
        if rat:
            entry["ratios"] = rat

        dcf = DCFCache.payload_entry(conn, ticker)
        if dcf:
            entry["dcf"] = dcf

        cmp = CompsCache.payload_entry(conn, ticker)
        if cmp:
            entry["comparables"] = cmp

        if entry:
            payload[ticker] = entry

    sd = SectorDataCache.payload_entry(conn)
    if sd:
        payload["sector_data"] = sd

    return payload
