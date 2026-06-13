"""Cache for sector-level valuation assumptions keyed by year (global, not per ticker)."""

from __future__ import annotations

from datetime import date

import duckdb

from backend.processing.schema import SectorData
from backend.services import financials as financials_service

from .session import now


class SectorDataCache:

    @staticmethod
    def get_or_fetch(
        conn: duckdb.DuckDBPyConnection,
        year: int | None,
    ) -> tuple[SectorData, bool]:
        resolved = int(year or date.today().year)
        conn.execute(
            "SELECT equity_risk_premium, long_term_growth_rate FROM sector_data WHERE year = ?",
            [resolved],
        )
        row = conn.fetchone()
        if row:
            return SectorData.model_validate({
                "equity_risk_premium": row[0],
                "long_term_growth_rate": row[1],
            }), True

        sd = financials_service.get_sector_data(resolved)
        SectorDataCache._store(conn, resolved, sd)
        return sd, False

    @staticmethod
    def _store(conn: duckdb.DuckDBPyConnection, year: int, sd: SectorData) -> None:
        conn.execute("""
            INSERT OR REPLACE INTO sector_data
                (year, equity_risk_premium, long_term_growth_rate, last_updated)
            VALUES (?, ?, ?, ?)
        """, [year, sd.equity_risk_premium, sd.long_term_growth_rate, now()])

    @staticmethod
    def catalog_entry(conn: duckdb.DuckDBPyConnection) -> list[int]:
        """Return sorted list of years for which sector data is cached."""
        conn.execute("SELECT year FROM sector_data ORDER BY year")
        return [row[0] for row in conn.fetchall()]

    @staticmethod
    def payload_entry(conn: duckdb.DuckDBPyConnection) -> dict | None:
        conn.execute(
            "SELECT year, equity_risk_premium, long_term_growth_rate FROM sector_data ORDER BY year"
        )
        rows = conn.fetchall()
        if not rows:
            return None
        return {
            str(r[0]): {"equity_risk_premium": r[1], "long_term_growth_rate": r[2]}
            for r in rows
        }
