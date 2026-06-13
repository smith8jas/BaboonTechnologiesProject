"""Cache for current market data (price, beta, shares, market cap) by ticker."""

from __future__ import annotations

import duckdb

from backend.processing.schema import MarketData
from backend.services import financials as financials_service

from .base import CacheHelpers
from .session import now


class MarketDataCache:

    @staticmethod
    def get_or_fetch(
        conn: duckdb.DuckDBPyConnection,
        ticker: str,
        include_rfr: bool = True,
    ) -> tuple[MarketData, bool]:
        t = CacheHelpers.ticker(ticker)
        if MarketDataCache._has(conn, t, include_rfr):
            return MarketDataCache._from_db(conn, t), True
        md = financials_service.get_market_data(t, include_rfr)
        MarketDataCache._store(conn, t, md, include_rfr)
        return md, False

    @staticmethod
    def _has(conn: duckdb.DuckDBPyConnection, ticker: str, include_rfr: bool) -> bool:
        conn.execute(
            "SELECT include_rfr FROM market_data WHERE ticker = ?",
            [ticker],
        )
        row = conn.fetchone()
        if not row:
            return False
        stored_rfr: bool = bool(row[0])
        # Hit if stored data already includes risk_free_rate, or if caller doesn't need it.
        return stored_rfr or not include_rfr

    @staticmethod
    def _from_db(conn: duckdb.DuckDBPyConnection, ticker: str) -> MarketData:
        conn.execute(
            "SELECT current_price, beta, shares_outstanding, market_cap, risk_free_rate "
            "FROM market_data WHERE ticker = ?",
            [ticker],
        )
        row = conn.fetchone()
        return MarketData.model_validate({
            "current_price": row[0],
            "beta": row[1],
            "shares_outstanding": row[2],
            "market_cap": row[3],
            "risk_free_rate": row[4],
        })

    @staticmethod
    def _store(
        conn: duckdb.DuckDBPyConnection,
        ticker: str,
        md: MarketData,
        include_rfr: bool,
    ) -> None:
        conn.execute("""
            INSERT OR REPLACE INTO market_data
                (ticker, current_price, beta, shares_outstanding, market_cap,
                 risk_free_rate, include_rfr, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            ticker, md.current_price, md.beta, md.shares_outstanding,
            md.market_cap, md.risk_free_rate, bool(include_rfr), now(),
        ])

    @staticmethod
    def catalog_entry(conn: duckdb.DuckDBPyConnection, ticker: str) -> dict | None:
        t = CacheHelpers.ticker(ticker)
        conn.execute(
            "SELECT include_rfr FROM market_data WHERE ticker = ?",
            [t],
        )
        row = conn.fetchone()
        if not row:
            return None
        return {
            "available": True,
            "include_rfr": bool(row[0]),
            "summary": f"Market data for {t} is available.",
        }

    @staticmethod
    def payload_entry(conn: duckdb.DuckDBPyConnection, ticker: str) -> dict | None:
        t = CacheHelpers.ticker(ticker)
        conn.execute(
            "SELECT current_price, beta, shares_outstanding, market_cap, risk_free_rate "
            "FROM market_data WHERE ticker = ?",
            [t],
        )
        row = conn.fetchone()
        if not row:
            return None
        return {
            "current_price": row[0],
            "beta": row[1],
            "shares_outstanding": row[2],
            "market_cap": row[3],
            "risk_free_rate": row[4],
        }
