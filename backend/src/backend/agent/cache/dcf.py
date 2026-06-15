"""Cache for DCF valuation scenarios, derived from financials, market, and sector data."""

from __future__ import annotations

import json

import duckdb

from backend.services import dcf_engine

from .base import CacheHelpers
from .financials import FinancialsCache
from .market_data import MarketDataCache
from .sector_data import SectorDataCache
from .session import get_session_cycle, now

SCENARIO_DEFAULT = "default"


class DCFCache:
    catalog_key = "dcf"
    catalog_category = "calculated"
    table_name = "dcf"

    @staticmethod
    def get_or_calculate(
        conn: duckdb.DuckDBPyConnection,
        ticker: str,
        span: int,
        year: int,
        session_id: str = "",
    ) -> tuple[dict, bool]:
        t = CacheHelpers.ticker(ticker)

        conn.execute(
            "SELECT span, sector_year, payload FROM dcf WHERE ticker = ? AND scenario = ?",
            [t, SCENARIO_DEFAULT],
        )
        row = conn.fetchone()
        if row and int(row[0] or 0) >= span and int(row[1] or 0) == int(year):
            return json.loads(row[2]), True

        hf = FinancialsCache.get_from_db(conn, t, span)
        md = MarketDataCache.get_from_db(conn, t, include_rfr=True)
        sd = SectorDataCache.get_from_db(conn, year)

        assumptions = dcf_engine.build_assumptions(hf, md, sd)
        valuation_inputs = dcf_engine.build_valuation_inputs(hf, md, sd, assumptions)
        result = dcf_engine.run_dcf(hf, valuation_inputs, assumptions)
        payload = result.model_dump(mode="json")

        conn.execute("""
            INSERT OR REPLACE INTO dcf
                (ticker, scenario, fiscal_year, sector_year, span, payload, cycle, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            t, SCENARIO_DEFAULT, result.fiscal_year, int(year), span,
            json.dumps(payload), get_session_cycle(session_id), now(),
        ])

        return payload, False

    @staticmethod
    def catalog_entry(conn: duckdb.DuckDBPyConnection, ticker: str) -> dict | None:
        t = CacheHelpers.ticker(ticker)
        conn.execute(
            "SELECT scenario, fiscal_year, payload FROM dcf WHERE ticker = ?",
            [t],
        )
        rows = conn.fetchall()
        if not rows:
            return None
        result = {}
        for scenario, fiscal_year, payload_json in rows:
            payload = json.loads(payload_json) if payload_json else {}
            projection_years = payload.get("projection_years", [])
            wacc = payload.get("wacc")
            terminal_growth = payload.get("terminal_growth")
            intrinsic_value_per_share = payload.get("intrinsic_value_per_share")
            last_projection = projection_years[-1] if projection_years else "N/A"
            wacc_str = f"{wacc:.1%}" if wacc is not None else "N/A"
            tg_str = f"{terminal_growth:.1%}" if terminal_growth is not None else "N/A"
            iv_str = f"${intrinsic_value_per_share:.2f}/share" if intrinsic_value_per_share is not None else "N/A"
            result[scenario] = {
                "available": True,
                "base_fiscal_year": fiscal_year,
                "projection_years": projection_years,
                "intrinsic_value_per_share": intrinsic_value_per_share,
                "summary": (
                    f"DCF valuation based on {fiscal_year} actuals, projected through {last_projection}. "
                    f"WACC={wacc_str}, terminal growth={tg_str}, intrinsic value={iv_str}."
                ),
            }
        return result

    @staticmethod
    def payload_entry(conn: duckdb.DuckDBPyConnection, ticker: str) -> dict | None:
        t = CacheHelpers.ticker(ticker)
        conn.execute(
            "SELECT scenario, payload FROM dcf WHERE ticker = ?",
            [t],
        )
        rows = conn.fetchall()
        if not rows:
            return None
        return {
            scenario: json.loads(payload_json)
            for scenario, payload_json in rows
            if payload_json is not None
        }
