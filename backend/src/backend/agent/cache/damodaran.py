"""Cache for Damodaran sector multiples (EV/Sales, P/S, Trailing PE) by industry."""

from __future__ import annotations

import duckdb

from backend.adapters.damodaran import fetch_ev_sales, fetch_price_sales, fetch_trailing_pe

from .session import get_session_cycle, now


class DamodaranSectorCache:
    table_name = "damodaran_sector"

    @staticmethod
    def get_or_fetch(
        conn: duckdb.DuckDBPyConnection,
        industry: str,
        session_id: str = "",
    ) -> dict:
        conn.execute(
            "SELECT ev_sales, price_sales, trailing_pe FROM damodaran_sector WHERE industry = ?",
            [industry],
        )
        row = conn.fetchone()
        if row:
            return {"ev_sales": row[0], "price_sales": row[1], "trailing_pe": row[2]}

        multiples = {
            "ev_sales":    fetch_ev_sales(industry),
            "price_sales": fetch_price_sales(industry),
            "trailing_pe": fetch_trailing_pe(industry),
        }

        conn.execute("""
            INSERT OR REPLACE INTO damodaran_sector
                (industry, ev_sales, price_sales, trailing_pe, cycle, last_updated)
            VALUES (?, ?, ?, ?, ?, ?)
        """, [
            industry,
            multiples["ev_sales"],
            multiples["price_sales"],
            multiples["trailing_pe"],
            get_session_cycle(session_id),
            now(),
        ])

        return multiples
