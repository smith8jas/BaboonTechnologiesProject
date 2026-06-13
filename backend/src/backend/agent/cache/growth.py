"""Cache for year-over-year growth-rate calculations, derived from financials."""

from __future__ import annotations

import json

import duckdb

from backend.services import growth as growth_service

from .base import CacheHelpers
from .financials import FinancialsCache
from .session import now

INCOME_STATEMENT = "income_statement"
BALANCE_SHEET = "balance_sheet"


class GrowthCache:

    @staticmethod
    def get_or_calculate(
        conn: duckdb.DuckDBPyConnection,
        ticker: str,
        span: int,
        statement: str,
    ) -> tuple[dict, bool]:
        t = CacheHelpers.ticker(ticker)

        conn.execute(
            "SELECT span, payload FROM growth_rates WHERE ticker = ? AND statement = ?",
            [t, statement],
        )
        row = conn.fetchone()
        if row and int(row[0] or 0) >= span:
            return json.loads(row[1]), True

        hf, _ = FinancialsCache.get_or_fetch(conn, t, span)
        if statement == INCOME_STATEMENT:
            payload = growth_service.get_income_statement_growth_rates(hf)
        elif statement == BALANCE_SHEET:
            payload = growth_service.get_balance_sheet_growth_rates(hf)
        else:
            raise ValueError(f"Unknown growth statement: {statement!r}")

        conn.execute("""
            INSERT OR REPLACE INTO growth_rates
                (ticker, statement, payload, span, last_updated)
            VALUES (?, ?, ?, ?, ?)
        """, [t, statement, json.dumps(payload, default=str), span, now()])

        return payload, False

    @staticmethod
    def catalog_entry(conn: duckdb.DuckDBPyConnection, ticker: str) -> dict | None:
        t = CacheHelpers.ticker(ticker)
        conn.execute(
            "SELECT statement, span FROM growth_rates WHERE ticker = ?",
            [t],
        )
        rows = conn.fetchall()
        if not rows:
            return None
        return {r[0]: {"available": True, "span": r[1]} for r in rows}

    @staticmethod
    def payload_entry(conn: duckdb.DuckDBPyConnection, ticker: str) -> dict | None:
        t = CacheHelpers.ticker(ticker)
        conn.execute(
            "SELECT statement, payload FROM growth_rates WHERE ticker = ?",
            [t],
        )
        rows = conn.fetchall()
        if not rows:
            return None
        return {r[0]: json.loads(r[1]) for r in rows if r[1] is not None}
