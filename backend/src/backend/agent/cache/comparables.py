"""Cache for comparable-company valuations (peer-based and Damodaran fallback)."""

from __future__ import annotations

import json

import duckdb

from backend.services import comparables as comparables_service

from .base import CacheHelpers
from .session import get_session_cycle, now


class CompsCache:
    catalog_key = "comparables"
    catalog_category = "calculated"
    table_name = "comparables"

    @staticmethod
    def get_or_calculate_peer(
        conn: duckdb.DuckDBPyConnection,
        ticker: str,
        peers: list[str],
        session_id: str = "",
    ) -> tuple[dict, bool]:
        t = CacheHelpers.ticker(ticker)
        peer_key = ",".join(sorted(p.strip().upper() for p in peers))

        conn.execute(
            "SELECT peer_key, payload FROM comparables WHERE ticker = ? AND method = 'peer'",
            [t],
        )
        row = conn.fetchone()
        if row and row[0] == peer_key:
            return json.loads(row[1]), True

        payload = comparables_service.peer_comps(conn, t, peers)

        conn.execute("""
            INSERT OR REPLACE INTO comparables
                (ticker, method, peer_key, payload, cycle, last_updated)
            VALUES (?, 'peer', ?, ?, ?, ?)
        """, [t, peer_key, json.dumps(payload, default=str), get_session_cycle(session_id), now()])

        return payload, False

    @staticmethod
    def get_or_calculate_damodaran(
        conn: duckdb.DuckDBPyConnection,
        ticker: str,
        session_id: str = "",
    ) -> tuple[dict, bool]:
        t = CacheHelpers.ticker(ticker)

        conn.execute(
            "SELECT payload FROM comparables WHERE ticker = ? AND method = 'damodaran'",
            [t],
        )
        row = conn.fetchone()
        if row:
            return json.loads(row[0]), True

        payload = comparables_service.damodaran_fallback(conn, t)

        conn.execute("""
            INSERT OR REPLACE INTO comparables
                (ticker, method, peer_key, payload, cycle, last_updated)
            VALUES (?, 'damodaran', NULL, ?, ?, ?)
        """, [t, json.dumps(payload, default=str), get_session_cycle(session_id), now()])

        return payload, False

    @staticmethod
    def catalog_entry(conn: duckdb.DuckDBPyConnection, ticker: str) -> dict | None:
        t = CacheHelpers.ticker(ticker)
        conn.execute(
            "SELECT method FROM comparables WHERE ticker = ?",
            [t],
        )
        rows = conn.fetchall()
        if not rows:
            return None
        return {r[0]: {"available": True} for r in rows}

    @staticmethod
    def payload_entry(conn: duckdb.DuckDBPyConnection, ticker: str) -> dict | None:
        t = CacheHelpers.ticker(ticker)
        conn.execute(
            "SELECT method, payload FROM comparables WHERE ticker = ?",
            [t],
        )
        rows = conn.fetchall()
        if not rows:
            return None
        return {
            method: json.loads(payload_json)
            for method, payload_json in rows
            if payload_json is not None
        }
