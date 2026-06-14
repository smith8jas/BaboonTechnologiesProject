"""Cache for financial ratio calculations, derived from financials."""

from __future__ import annotations

import json

import duckdb

from backend.services import ratio as ratio_service

from .base import CacheHelpers
from .financials import FinancialsCache
from .session import get_session_cycle, now

class RatiosCache:

    _RATIO_FUNCS = {
        "liquidity": ratio_service.get_liquidity_ratios,
        "solvency": ratio_service.get_solvency_ratios,
        "profitability": ratio_service.get_profitability_ratios,
        "efficiency": ratio_service.get_efficiency_ratios,
    }

    @staticmethod
    def get_or_calculate(
        conn: duckdb.DuckDBPyConnection,
        ticker: str,
        span: int,
        ratio_type: str,
        session_id: str = "",
    ) -> tuple[dict, bool]:
        t = CacheHelpers.ticker(ticker)

        conn.execute(
            "SELECT span, payload FROM ratios WHERE ticker = ? AND ratio_type = ?",
            [t, ratio_type],
        )
        row = conn.fetchone()
        if row and int(row[0] or 0) >= span:
            return json.loads(row[1]), True

        hf, _ = FinancialsCache.get_or_fetch(conn, t, span, session_id=session_id)
        fn = RatiosCache._RATIO_FUNCS.get(ratio_type)
        if fn is None:
            raise ValueError(f"Unknown ratio type: {ratio_type!r}. Valid: {sorted(RatiosCache._RATIO_FUNCS)}")
        payload = fn(hf)

        conn.execute("""
            INSERT OR REPLACE INTO ratios
                (ticker, ratio_type, payload, span, cycle, last_updated)
            VALUES (?, ?, ?, ?, ?, ?)
        """, [t, ratio_type, json.dumps(payload, default=str), span, get_session_cycle(session_id), now()])

        return payload, False

    @staticmethod
    def catalog_entry(conn: duckdb.DuckDBPyConnection, ticker: str) -> dict | None:
        t = CacheHelpers.ticker(ticker)
        conn.execute(
            "SELECT ratio_type, span FROM ratios WHERE ticker = ?",
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
            "SELECT ratio_type, payload FROM ratios WHERE ticker = ?",
            [t],
        )
        rows = conn.fetchall()
        if not rows:
            return None
        return {r[0]: json.loads(r[1]) for r in rows if r[1] is not None}
