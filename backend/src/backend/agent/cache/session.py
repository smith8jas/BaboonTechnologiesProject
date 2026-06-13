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
from datetime import datetime, timezone

import duckdb

logger = logging.getLogger(__name__)

# session_id → absolute path of the session's .duckdb temp file
_REGISTRY: dict[str, str] = {}

# ---------------------------------------------------------------------------
# Schema — one CREATE TABLE per data type.
# All writers use INSERT OR REPLACE (upsert), so these tables are append-safe.
# ---------------------------------------------------------------------------

_DDL: tuple[str, ...] = (
    # One row per company — populated alongside the first financials fetch.
    """
    CREATE TABLE IF NOT EXISTS companies (
        ticker                  VARCHAR PRIMARY KEY,
        name                    VARCHAR,
        cik                     VARCHAR,
        sic                     INTEGER,
        industry                VARCHAR,
        fiscal_year_end         VARCHAR,
        entity_type             VARCHAR,
        filer_category          VARCHAR,
        state_of_incorporation  VARCHAR,
        website                 VARCHAR,
        phone                   VARCHAR,
        last_updated            TIMESTAMPTZ
    )
    """,

    # One row per (ticker, fiscal_year).
    # Income-statement, balance-sheet, cash-flow, and per-share fields are
    # all flattened into columns.  Cash-flow fields that share names with the
    # income statement (net_income, interest_expense) are prefixed with cf_.
    """
    CREATE TABLE IF NOT EXISTS financials (
        ticker                      VARCHAR  NOT NULL,
        fiscal_year                 VARCHAR  NOT NULL,
        period_end                  DATE,
        -- income statement
        revenue                     DOUBLE,
        cogs                        DOUBLE,
        gross_profit                DOUBLE,
        ebit                        DOUBLE,
        ebiat                       DOUBLE,
        ebitda                      DOUBLE,
        tax_expense                 DOUBLE,
        net_income                  DOUBLE,
        interest_expense            DOUBLE,
        depreciation_expense        DOUBLE,
        -- balance sheet
        total_current_assets        DOUBLE,
        cash                        DOUBLE,
        total_assets                DOUBLE,
        inventory                   DOUBLE,
        accounts_receivable         DOUBLE,
        accounts_payable            DOUBLE,
        short_term_debt             DOUBLE,
        long_term_debt              DOUBLE,
        total_current_liabilities   DOUBLE,
        total_liabilities           DOUBLE,
        total_equity                DOUBLE,
        net_working_capital         DOUBLE,
        -- cash flow (prefixed to avoid collision with income statement columns)
        cf_net_income               DOUBLE,
        cf_interest_expense         DOUBLE,
        capex                       DOUBLE,
        depreciation_amortization   DOUBLE,
        cfo                         DOUBLE,
        fcf                         DOUBLE,
        -- per share
        basic_shares                DOUBLE,
        diluted_shares              DOUBLE,
        last_updated                TIMESTAMPTZ,
        PRIMARY KEY (ticker, fiscal_year)
    )
    """,

    # One row per ticker — current snapshot, not time-series.
    """
    CREATE TABLE IF NOT EXISTS market_data (
        ticker              VARCHAR PRIMARY KEY,
        current_price       DOUBLE,
        beta                DOUBLE,
        shares_outstanding  DOUBLE,
        market_cap          DOUBLE,
        risk_free_rate      DOUBLE,
        include_rfr         BOOLEAN,
        last_updated        TIMESTAMPTZ
    )
    """,

    # One row per year — global, not per-ticker.
    """
    CREATE TABLE IF NOT EXISTS sector_data (
        year                    INTEGER PRIMARY KEY,
        equity_risk_premium     DOUBLE,
        long_term_growth_rate   DOUBLE,
        last_updated            TIMESTAMPTZ
    )
    """,

    # One row per (ticker, fiscal_year, statement, field).
    # statement ∈ {"income_statement", "balance_sheet"}
    """
    CREATE TABLE IF NOT EXISTS growth_rates (
        ticker          VARCHAR  NOT NULL,
        fiscal_year     VARCHAR  NOT NULL,
        statement       VARCHAR  NOT NULL,
        field           VARCHAR  NOT NULL,
        value           DOUBLE,
        span            INTEGER,
        last_updated    TIMESTAMPTZ,
        PRIMARY KEY (ticker, fiscal_year, statement, field)
    )
    """,

    # One row per (ticker, fiscal_year, ratio_type, field).
    # ratio_type ∈ {"liquidity", "solvency", "profitability", "efficiency"}
    """
    CREATE TABLE IF NOT EXISTS ratios (
        ticker          VARCHAR  NOT NULL,
        fiscal_year     VARCHAR  NOT NULL,
        ratio_type      VARCHAR  NOT NULL,
        field           VARCHAR  NOT NULL,
        value           DOUBLE,
        span            INTEGER,
        last_updated    TIMESTAMPTZ,
        PRIMARY KEY (ticker, fiscal_year, ratio_type, field)
    )
    """,

    # One row per (ticker, scenario).
    # List-valued DCF outputs are stored as native DuckDB arrays.
    """
    CREATE TABLE IF NOT EXISTS dcf (
        ticker                          VARCHAR  NOT NULL,
        scenario                        VARCHAR  NOT NULL,
        fiscal_year                     VARCHAR,
        intrinsic_value_per_share       DOUBLE,
        terminal_value                  DOUBLE,
        pv_terminal                     DOUBLE,
        tv_pct_of_ev                    DOUBLE,
        enterprise_value                DOUBLE,
        projection_years                VARCHAR[],
        projected_fcff                  DOUBLE[],
        pv_fcff                         DOUBLE[],
        projected_revenue               DOUBLE[],
        projected_ebit                  DOUBLE[],
        projected_ebiat                 DOUBLE[],
        projected_da                    DOUBLE[],
        projected_capex                 DOUBLE[],
        projected_delta_nwc             DOUBLE[],
        pv_factors                      DOUBLE[],
        falled_back_to_risk_free_rate   BOOLEAN,
        sector_year                     INTEGER,
        span                            INTEGER,
        last_updated                    TIMESTAMPTZ,
        PRIMARY KEY (ticker, scenario)
    )
    """,

    # One row per (ticker, method).
    # method ∈ {"peer", "damodaran"}
    # payload stored as JSON because its shape varies by method.
    """
    CREATE TABLE IF NOT EXISTS comparables (
        ticker          VARCHAR  NOT NULL,
        method          VARCHAR  NOT NULL,
        peer_key        VARCHAR,
        payload         JSON,
        last_updated    TIMESTAMPTZ,
        PRIMARY KEY (ticker, method)
    )
    """,
)


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

    conn = duckdb.connect(path)
    try:
        for ddl in _DDL:
            conn.execute(ddl)
    finally:
        conn.close()

    _REGISTRY[session_id] = path
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
    if path and os.path.exists(path):
        try:
            os.unlink(path)
        except OSError:
            logger.warning("Could not delete session file: %s", path)
    logger.info("Cache session closed: %s", session_id)


# ---------------------------------------------------------------------------
# Shared utility
# ---------------------------------------------------------------------------

def now() -> str:
    """UTC timestamp used by all cache writers for last_updated columns."""
    return datetime.now(timezone.utc).isoformat()
