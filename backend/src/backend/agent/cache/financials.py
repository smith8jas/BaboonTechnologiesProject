"""Cache for historical financial statements, backed by DuckDB."""

from __future__ import annotations

from datetime import date as date_type
from typing import Any

import duckdb

from backend.processing.schema import HistoricalFinancials
from backend.services import financials as financials_service

from .base import CacheHelpers
from .session import now


def _fy_str(year: Any) -> str:
    """Normalize a fiscal-year label to the 'FY2023' format stored in the DB."""
    s = str(year).strip().upper()
    return s if s.startswith("FY") else f"FY{s}"


def _row_to_period(row: dict) -> dict:
    """Map a flat financials row to a FinancialPeriod-compatible dict."""
    return {
        "fiscal_year": row["fiscal_year"],
        "period_end": row["period_end"],
        "income_statement": {
            "revenue": row["revenue"],
            "cogs": row["cogs"],
            "gross_profit": row["gross_profit"],
            "ebit": row["ebit"],
            "tax_expense": row["tax_expense"],
            "net_income": row["net_income"],
            "interest_expense": row["interest_expense"],
            "depreciation_expense": row["depreciation_expense"],
        },
        "balance_sheet": {
            "total_current_assets": row["total_current_assets"],
            "cash": row["cash"],
            "total_assets": row["total_assets"],
            "inventory": row["inventory"],
            "accounts_receivable": row["accounts_receivable"],
            "accounts_payable": row["accounts_payable"],
            "short_term_debt": row["short_term_debt"],
            "long_term_debt": row["long_term_debt"],
            "total_current_liabilities": row["total_current_liabilities"],
            "total_liabilities": row["total_liabilities"],
            "total_equity": row["total_equity"],
        },
        "cash_flow": {
            "net_income": row["cf_net_income"],
            "interest_expense": row["cf_interest_expense"],
            "capex": row["capex"],
            "depreciation_amortization": row["depreciation_amortization"],
            "cfo": row["cfo"],
        },
        "per_share": {
            "basic_shares": row["basic_shares"],
            "diluted_shares": row["diluted_shares"],
        },
    }


def _fetch_rows(conn: duckdb.DuckDBPyConnection, query: str, params: list) -> list[dict]:
    conn.execute(query, params)
    cols = [d[0] for d in conn.description]
    return [dict(zip(cols, row)) for row in conn.fetchall()]


def _build_hf(conn: duckdb.DuckDBPyConnection, ticker: str, rows: list[dict]) -> HistoricalFinancials:
    """Build a HistoricalFinancials from DB rows, pulling company metadata from companies table."""
    conn.execute("SELECT * FROM companies WHERE ticker = ?", [ticker])
    cols = [d[0] for d in conn.description]
    c_row = conn.fetchone()
    if c_row:
        c = dict(zip(cols, c_row))
        meta = {
            "cik": c.get("cik") or "",
            "name": c.get("name") or ticker,
            "sic": c.get("sic"),
            "industry": c.get("industry"),
            "fiscal_year_end": c.get("fiscal_year_end"),
            "entity_type": c.get("entity_type"),
            "filer_category": c.get("filer_category"),
            "state_of_incorporation": c.get("state_of_incorporation"),
            "website": c.get("website"),
            "phone": c.get("phone"),
        }
    else:
        meta = {"cik": "", "name": ticker}

    return HistoricalFinancials.model_validate({
        "ticker": ticker,
        "metadata": meta,
        "periods": [_row_to_period(r) for r in rows],
    })


class FinancialsCache:

    @staticmethod
    def get_or_fetch(
        conn: duckdb.DuckDBPyConnection,
        ticker: str,
        span: int = 5,
        fiscal_years: list[int] | None = None,
    ) -> tuple[HistoricalFinancials, bool]:
        t = CacheHelpers.ticker(ticker)

        if fiscal_years:
            if FinancialsCache._has_fiscal_years(conn, t, fiscal_years):
                return FinancialsCache._from_db_by_years(conn, t, fiscal_years), True
            needed_span = max(span, date_type.today().year - min(int(y) for y in fiscal_years) + 2)
            hf = financials_service.get_cached_financials(t, int(needed_span))
            FinancialsCache._store(conn, hf, int(needed_span))
            return FinancialsCache._filter_by_years(hf, fiscal_years), False

        if FinancialsCache._has(conn, t, span):
            return FinancialsCache._from_db(conn, t, span), True

        hf = financials_service.get_cached_financials(t, int(span))
        FinancialsCache._store(conn, hf, int(span))
        return hf, False

    @staticmethod
    def _has(conn: duckdb.DuckDBPyConnection, ticker: str, span: int) -> bool:
        conn.execute(
            "SELECT COUNT(DISTINCT fiscal_year) FROM financials WHERE ticker = ?",
            [ticker],
        )
        row = conn.fetchone()
        return bool(row and row[0] >= span)

    @staticmethod
    def _has_fiscal_years(conn: duckdb.DuckDBPyConnection, ticker: str, fiscal_years: list[int]) -> bool:
        targets = {_fy_str(y) for y in fiscal_years}
        placeholders = ", ".join("?" * len(targets))
        conn.execute(
            f"SELECT DISTINCT fiscal_year FROM financials WHERE ticker = ? AND fiscal_year IN ({placeholders})",
            [ticker, *targets],
        )
        found = {row[0] for row in conn.fetchall()}
        return targets.issubset(found)

    @staticmethod
    def _from_db(conn: duckdb.DuckDBPyConnection, ticker: str, span: int) -> HistoricalFinancials:
        rows = _fetch_rows(
            conn,
            "SELECT * FROM financials WHERE ticker = ? ORDER BY period_end DESC LIMIT ?",
            [ticker, span],
        )
        rows.reverse()  # oldest → newest
        return _build_hf(conn, ticker, rows)

    @staticmethod
    def _from_db_by_years(
        conn: duckdb.DuckDBPyConnection, ticker: str, fiscal_years: list[int]
    ) -> HistoricalFinancials:
        targets = [_fy_str(y) for y in fiscal_years]
        placeholders = ", ".join("?" * len(targets))
        rows = _fetch_rows(
            conn,
            f"SELECT * FROM financials WHERE ticker = ? AND fiscal_year IN ({placeholders}) ORDER BY period_end",
            [ticker, *targets],
        )
        return _build_hf(conn, ticker, rows)

    @staticmethod
    def _filter_by_years(hf: HistoricalFinancials, fiscal_years: list[int]) -> HistoricalFinancials:
        targets = {_fy_str(y) for y in fiscal_years}
        filtered = [p for p in hf.periods if _fy_str(p.fiscal_year or p.period_end.year) in targets]
        return HistoricalFinancials.model_validate({
            "ticker": hf.ticker,
            "metadata": hf.metadata.model_dump(mode="json"),
            "periods": [p.model_dump(mode="json") for p in filtered],
        })

    @staticmethod
    def _store(conn: duckdb.DuckDBPyConnection, hf: HistoricalFinancials, span: int) -> None:
        t = hf.ticker
        m = hf.metadata
        ts = now()

        conn.execute("""
            INSERT OR REPLACE INTO companies
                (ticker, name, cik, sic, industry, fiscal_year_end,
                 entity_type, filer_category, state_of_incorporation,
                 website, phone, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            t, m.name, m.cik, m.sic, m.industry, m.fiscal_year_end,
            m.entity_type, m.filer_category, m.state_of_incorporation,
            m.website, m.phone, ts,
        ])

        for period in hf.periods:
            IS = period.income_statement
            BS = period.balance_sheet
            CF = period.cash_flow
            PS = period.per_share
            fy = _fy_str(period.fiscal_year or period.period_end.year)

            conn.execute("""
                INSERT OR REPLACE INTO financials (
                    ticker, fiscal_year, period_end,
                    revenue, cogs, gross_profit, ebit, ebiat, ebitda,
                    tax_expense, net_income, interest_expense, depreciation_expense,
                    total_current_assets, cash, total_assets, inventory,
                    accounts_receivable, accounts_payable, short_term_debt, long_term_debt,
                    total_current_liabilities, total_liabilities, total_equity, net_working_capital,
                    cf_net_income, cf_interest_expense, capex, depreciation_amortization, cfo, fcf,
                    basic_shares, diluted_shares, last_updated
                ) VALUES (
                    ?, ?, ?,
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?
                )
            """, [
                t, fy, period.period_end.isoformat(),
                IS.revenue, IS.cogs, IS.gross_profit, IS.ebit, IS.ebiat, IS.ebitda,
                IS.tax_expense, IS.net_income, IS.interest_expense, IS.depreciation_expense,
                BS.total_current_assets, BS.cash, BS.total_assets, BS.inventory,
                BS.accounts_receivable, BS.accounts_payable, BS.short_term_debt, BS.long_term_debt,
                BS.total_current_liabilities, BS.total_liabilities, BS.total_equity, BS.net_working_capital,
                CF.net_income, CF.interest_expense, CF.capex, CF.depreciation_amortization, CF.cfo, CF.fcf,
                PS.basic_shares, PS.diluted_shares, ts,
            ])

    @staticmethod
    def catalog_entry(conn: duckdb.DuckDBPyConnection, ticker: str) -> dict | None:
        """Return catalog metadata for this ticker's financials, or None if not cached."""
        t = CacheHelpers.ticker(ticker)
        conn.execute(
            "SELECT fiscal_year, period_end FROM financials WHERE ticker = ? ORDER BY period_end",
            [t],
        )
        rows = conn.fetchall()
        if not rows:
            return None
        fiscal_years = [r[0] for r in rows]
        period_ends = [str(r[1]) for r in rows]
        return {
            "available": True,
            "fiscal_years": fiscal_years,
            "period_ends": period_ends,
            "max_span": len(fiscal_years),
            "summary": (
                f"Historical financials for {t} available for "
                f"{fiscal_years[0]}–{fiscal_years[-1]}."
            ),
        }

    @staticmethod
    def payload_entry(conn: duckdb.DuckDBPyConnection, ticker: str) -> dict | None:
        """Return the full financials payload for this ticker, or None if not cached."""
        t = CacheHelpers.ticker(ticker)
        conn.execute("SELECT * FROM companies WHERE ticker = ?", [t])
        cols = [d[0] for d in conn.description]
        c_row = conn.fetchone()
        if not c_row:
            return None
        c = dict(zip(cols, c_row))
        rows = _fetch_rows(
            conn,
            "SELECT * FROM financials WHERE ticker = ? ORDER BY period_end",
            [t],
        )
        return {
            "metadata": {k: c.get(k) for k in (
                "name", "cik", "sic", "industry", "fiscal_year_end",
                "entity_type", "filer_category", "state_of_incorporation",
                "website", "phone",
            )},
            "periods": [_row_to_period(r) for r in rows],
        }
