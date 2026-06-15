"""DuckDB session management and schema for the agent data cache.

One session = one agent conversation (keyed by thread_id).
Each session gets its own temporary .duckdb file so connections opened from
different threads (asyncio.to_thread) are fully isolated.

Public API
----------
create_session(session_id)   -- call once at conversation start
open_connection(session_id)  -- call per operation; caller must close()
close_session(session_id)    -- call when conversation ends
now()                        -- UTC timestamp string used by all writers
"""

from __future__ import annotations

import logging
import os
import tempfile
import types as _types
from datetime import date as _date, datetime, timezone
from typing import Union, get_args, get_origin

import duckdb

from backend.processing.schema import (
    BalanceSheet,
    CashFlowStatement,
    CompanyMetadata,
    IncomeStatement,
    MarketData,
    PerShare,
    SectorData,
)

logger = logging.getLogger(__name__)

# session_id → absolute path of the session's .duckdb temp file
_REGISTRY: dict[str, str] = {}

# session_id → current query cycle number (set by router before each tool run)
_CYCLE_REGISTRY: dict[str, int] = {}


def set_session_cycle(session_id: str, cycle: int) -> None:
    """Record the current query cycle for this session so cache writers can tag rows."""
    _CYCLE_REGISTRY[session_id] = cycle


def get_session_cycle(session_id: str) -> int:
    """Return the current cycle for this session, defaulting to 1."""
    return _CYCLE_REGISTRY.get(session_id, 1)

# ---------------------------------------------------------------------------
# Schema generation — column names and types derived from Pydantic models
# so the DDL stays in sync with processing/schema.py automatically.
# ---------------------------------------------------------------------------

_DUCK_TYPE_MAP: dict = {
    float: "DOUBLE",
    int:   "INTEGER",
    str:   "VARCHAR",
    bool:  "BOOLEAN",
    _date: "DATE",
}


def _duck_type(annotation) -> str:
    """Resolve a Python type annotation to a DuckDB column type string."""
    origin = get_origin(annotation)
    # Handle both `Optional[X]` (typing.Union) and `X | None` (types.UnionType on 3.10+)
    if origin is Union or (
        hasattr(_types, "UnionType") and isinstance(annotation, _types.UnionType)
    ):
        non_none = [a for a in get_args(annotation) if a is not type(None)]
        if non_none:
            return _duck_type(non_none[0])
    return _DUCK_TYPE_MAP.get(annotation, "VARCHAR")


def _model_cols(model: type, rename: dict[str, str] | None = None) -> list[str]:
    """Return DDL column lines derived from a Pydantic model's fields and computed fields."""
    rename = rename or {}
    cols = []
    for name, field in model.model_fields.items():
        col_name = rename.get(name, name)
        cols.append(f"        {col_name:<35} {_duck_type(field.annotation)}")
    for name, computed in model.model_computed_fields.items():
        col_name = rename.get(name, name)
        cols.append(f"        {col_name:<35} {_duck_type(computed.return_type)}")
    return cols


def _join(*column_lists: list[str]) -> str:
    return ",\n".join(col for cols in column_lists for col in cols)


# CashFlowStatement shares two field names with IncomeStatement.
# Only those two are prefixed; the remaining CF fields have no collision.
_CF_RENAME = {"net_income": "cf_net_income", "interest_expense": "cf_interest_expense"}


def _build_ddl() -> tuple[str, ...]:
    """Build all CREATE TABLE statements, deriving columns from Pydantic schema models."""
    return (
        # One row per company — populated alongside the first financials fetch.
        f"""
    CREATE TABLE IF NOT EXISTS companies (
        ticker                              VARCHAR PRIMARY KEY,
{_join(_model_cols(CompanyMetadata))},
        cycle                               INTEGER DEFAULT 0,
        last_updated                        TIMESTAMPTZ
    )
    """,

        # One row per (ticker, fiscal_year) — all statement fields flattened into columns.
        # Cash-flow fields that share names with IS (net_income, interest_expense) are cf_-prefixed.
        f"""
    CREATE TABLE IF NOT EXISTS financials (
        ticker                              VARCHAR  NOT NULL,
        fiscal_year                         VARCHAR  NOT NULL,
        period_end                          DATE,
{_join(
    _model_cols(IncomeStatement),
    _model_cols(BalanceSheet),
    _model_cols(CashFlowStatement, rename=_CF_RENAME),
    _model_cols(PerShare),
)},
        cycle                               INTEGER DEFAULT 0,
        last_updated                        TIMESTAMPTZ,
        PRIMARY KEY (ticker, fiscal_year)
    )
    """,

        # One row per ticker — current snapshot, not time-series.
        f"""
    CREATE TABLE IF NOT EXISTS market_data (
        ticker                              VARCHAR PRIMARY KEY,
{_join(_model_cols(MarketData))},
        include_rfr                         BOOLEAN,
        cycle                               INTEGER DEFAULT 0,
        last_updated                        TIMESTAMPTZ
    )
    """,

        # One row per year — global Damodaran sector data, not per-ticker.
        f"""
    CREATE TABLE IF NOT EXISTS sector_data (
        year                                INTEGER PRIMARY KEY,
{_join(_model_cols(SectorData))},
        cycle                               INTEGER DEFAULT 0,
        last_updated                        TIMESTAMPTZ
    )
    """,

        # growth_rates, ratios, dcf, comparables store computed payloads as JSON —
        # no Pydantic model maps directly to these column layouts.
        """
    CREATE TABLE IF NOT EXISTS growth_rates (
        ticker       VARCHAR  NOT NULL,
        statement    VARCHAR  NOT NULL,
        payload      JSON,
        span         INTEGER,
        cycle        INTEGER DEFAULT 0,
        last_updated TIMESTAMPTZ,
        PRIMARY KEY (ticker, statement)
    )
    """,

        """
    CREATE TABLE IF NOT EXISTS ratios (
        ticker       VARCHAR  NOT NULL,
        ratio_type   VARCHAR  NOT NULL,
        payload      JSON,
        span         INTEGER,
        cycle        INTEGER DEFAULT 0,
        last_updated TIMESTAMPTZ,
        PRIMARY KEY (ticker, ratio_type)
    )
    """,

        """
    CREATE TABLE IF NOT EXISTS dcf (
        ticker       VARCHAR  NOT NULL,
        scenario     VARCHAR  NOT NULL,
        fiscal_year  VARCHAR,
        sector_year  INTEGER,
        span         INTEGER,
        payload      JSON,
        cycle        INTEGER DEFAULT 0,
        last_updated TIMESTAMPTZ,
        PRIMARY KEY (ticker, scenario)
    )
    """,

        """
    CREATE TABLE IF NOT EXISTS comparables (
        ticker       VARCHAR  NOT NULL,
        method       VARCHAR  NOT NULL,
        peer_key     VARCHAR,
        payload      JSON,
        cycle        INTEGER DEFAULT 0,
        last_updated TIMESTAMPTZ,
        PRIMARY KEY (ticker, method)
    )
    """,

        """
    CREATE TABLE IF NOT EXISTS damodaran_sector (
        industry     VARCHAR PRIMARY KEY,
        ev_sales     DOUBLE,
        price_sales  DOUBLE,
        trailing_pe  DOUBLE,
        cycle        INTEGER DEFAULT 0,
        last_updated TIMESTAMPTZ
    )
    """,
    )


_DDL: tuple[str, ...] = _build_ddl()


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------

def create_session(session_id: str) -> None:
    """Create a temp .duckdb file and initialise all tables for this session.

    Idempotent — safe to call multiple times with the same session_id.
    """
    if session_id in _REGISTRY:
        return

    fd, path = tempfile.mkstemp(
        suffix=".duckdb",
        prefix=f"agent_{session_id[:8]}_",
    )
    os.close(fd)
    os.unlink(path)  # mkstemp creates an empty file; DuckDB needs a non-existent path to init fresh

    conn = duckdb.connect(path)
    try:
        for ddl in _DDL:
            conn.execute(ddl)
    finally:
        conn.close()

    _REGISTRY[session_id] = path
    _CYCLE_REGISTRY[session_id] = 0
    logger.info("Cache session created: %s → %s", session_id, path)


def open_connection(session_id: str) -> duckdb.DuckDBPyConnection:
    """Return a fresh connection to this session's database.

    Caller is responsible for calling .close() when done.
    Opening a new connection per operation keeps threads isolated —
    DuckDB serialises concurrent writes to the same file automatically.
    """
    if session_id not in _REGISTRY:
        raise KeyError(
            f"No cache session for '{session_id}'. Call create_session() first."
        )
    return duckdb.connect(_REGISTRY[session_id])


def close_session(session_id: str) -> None:
    """Delete the session's database file and remove it from the registry."""
    path = _REGISTRY.pop(session_id, None)
    _CYCLE_REGISTRY.pop(session_id, None)
    if path and os.path.exists(path):
        try:
            os.unlink(path)
        except OSError:
            logger.warning("Could not delete session file: %s", path)
    logger.info("Cache session closed: %s", session_id)


# How many recent cycles to retain per data category.
_CALC_KEEP = 2   # keep last 2 cycles of calculated data  → delete first 3 of every 5
_SEARCH_KEEP = 3 # keep last 3 cycles of searched data    → delete first 2 of every 5


def purge_old_data(session_id: str, current_cycle: int) -> None:
    """Delete stale rows from all cache tables based on cycle thresholds.

    Called by the router every 5 cycles. Calculated data (cheap to recompute)
    is purged more aggressively than searched data (requires external API calls).
    """
    calc_threshold = current_cycle - _CALC_KEEP
    search_threshold = current_cycle - _SEARCH_KEEP

    conn = open_connection(session_id)
    try:
        if calc_threshold >= 1:
            conn.execute("DELETE FROM growth_rates WHERE cycle <= ?", [calc_threshold])
            conn.execute("DELETE FROM ratios WHERE cycle <= ?", [calc_threshold])
            conn.execute("DELETE FROM dcf WHERE cycle <= ?", [calc_threshold])
            conn.execute("DELETE FROM comparables WHERE cycle <= ?", [calc_threshold])

        if search_threshold >= 1:
            conn.execute("DELETE FROM financials WHERE cycle <= ?", [search_threshold])
            conn.execute("DELETE FROM market_data WHERE cycle <= ?", [search_threshold])
            conn.execute("DELETE FROM sector_data WHERE cycle <= ?", [search_threshold])
            conn.execute("DELETE FROM damodaran_sector WHERE cycle <= ?", [search_threshold])
            conn.execute("""
                DELETE FROM companies
                WHERE ticker NOT IN (SELECT ticker FROM financials)
                  AND ticker NOT IN (SELECT ticker FROM market_data)
            """)
    finally:
        conn.close()

    logger.info(
        "Cache purged for session %s at cycle %d (calc_threshold=%d, search_threshold=%d)",
        session_id, current_cycle, calc_threshold, search_threshold,
    )


# ---------------------------------------------------------------------------
# Shared utility
# ---------------------------------------------------------------------------

def now() -> str:
    """UTC timestamp used by all cache writers for last_updated columns."""
    return datetime.now(timezone.utc).isoformat()
