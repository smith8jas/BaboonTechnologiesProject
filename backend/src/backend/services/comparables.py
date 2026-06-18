"""
services/comparables.py
Comparable company analysis — peer-based multiples and Damodaran sector fallback.

Data files required (commit to repo):
  backend/data/sic.csv  — SIC int → Damodaran industry name

Schema dependency:
  CompanyMetadata must include `sic: Optional[int]`.
  Add to processing/schema.py if not already present.

Pure functions only — no I/O, no agent/cache dependency. The caller (the
get_comps_valuation tool) is responsible for resolving HistoricalFinancials/
MarketData objects from research_messages (and fetching Damodaran sector
multiples on a miss) before calling into this module.
"""

from __future__ import annotations

import statistics
from pathlib import Path

import pandas as pd

from backend.processing.schema import HistoricalFinancials, MarketData

# ---------------------------------------------------------------------------
# SIC → Damodaran industry map
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
_sic_map: dict[int, str] | None = None


def _load_sic_map() -> dict[int, str]:
    global _sic_map
    if _sic_map is None:
        df = pd.read_csv(_DATA_DIR / "sic.csv")
        _sic_map = dict(zip(df["SIC Code"].astype(int), df["Damodaran Industry"]))
    return _sic_map


def _damodaran_industry(sic: int) -> str | None:
    return _load_sic_map().get(sic)


# ---------------------------------------------------------------------------
# Sector gate
# ---------------------------------------------------------------------------

_FINANCIAL_SIC_RANGE = range(6000, 6800)


def _is_financial(sic: int) -> bool:
    return sic in _FINANCIAL_SIC_RANGE


# ---------------------------------------------------------------------------
# Multiple primitives  (internal — not @tool)
# All return None on bad/zero/negative denominators.
# ---------------------------------------------------------------------------

def _enterprise_value(
    mkt_cap: float | None,
    long_term_debt: float | None,
    cash: float | None,
) -> float | None:
    if any(v is None for v in [mkt_cap, long_term_debt, cash]):
        return None
    return mkt_cap + long_term_debt - cash  # type: ignore[operator]


def _pe(mkt_cap: float | None, net_income: float | None) -> float | None:
    if not mkt_cap or not net_income or net_income <= 0:
        return None
    return mkt_cap / net_income


def _ev_sales(ev: float | None, revenue: float | None) -> float | None:
    if ev is None or not revenue or revenue <= 0:
        return None
    return ev / revenue


def _ev_ebitda(ev: float | None, ebit: float | None, da: float | None) -> float | None:
    ebitda = (ebit or 0.0) + (da or 0.0)
    if ev is None or ebitda <= 0:
        return None
    return ev / ebitda


def _ps(mkt_cap: float | None, revenue: float | None) -> float | None:
    if not mkt_cap or not revenue or revenue <= 0:
        return None
    return mkt_cap / revenue


def _pb(mkt_cap: float | None, total_equity: float | None) -> float | None:
    if not mkt_cap or not total_equity or total_equity <= 0:
        return None
    return mkt_cap / total_equity


# ---------------------------------------------------------------------------
# Per-company multiples
# ---------------------------------------------------------------------------

def _compute_multiples(fin: HistoricalFinancials, mkt: MarketData) -> dict:
    period = fin.periods[-1]
    IS  = period.income_statement
    BS  = period.balance_sheet
    CFS = period.cash_flow          

    ev = _enterprise_value(mkt.market_cap, BS.long_term_debt, BS.cash)

    raw = {
        "P/E":       _pe(mkt.market_cap, IS.net_income),
        "EV/EBITDA": _ev_ebitda(ev, IS.ebit, CFS.depreciation_amortization),
        "EV/Sales":  _ev_sales(ev, IS.revenue),
        "P/S":       _ps(mkt.market_cap, IS.revenue),
        "P/B":       _pb(mkt.market_cap, BS.total_equity),
    }

    notes: list[str] = []
    multiples: dict[str, float | None] = {}

    for name, val in raw.items():
        if val is None:
            notes.append(f"{name}: null (missing or invalid inputs)")
            multiples[name] = None
        elif val < 0:
            notes.append(f"{name}: negative — excluded from peer median")
            multiples[name] = None
        else:
            multiples[name] = round(val, 2)

    return {"multiples": multiples, "notes": notes}


# ---------------------------------------------------------------------------
# Peer aggregation
# ---------------------------------------------------------------------------

def _median_multiples(peer_results: list[dict]) -> dict[str, float | None]:
    keys = ["P/E", "EV/EBITDA", "EV/Sales", "P/S", "P/B"]
    out: dict[str, float | None] = {}
    for k in keys:
        vals = [p["multiples"][k] for p in peer_results if p["multiples"].get(k) is not None]
        out[k] = round(statistics.median(vals), 2) if vals else None
    return out


def _implied_per_share(
    target_fin: HistoricalFinancials,
    target_mkt: MarketData,
    medians: dict[str, float | None],
) -> dict[str, float | None]:
    period = target_fin.periods[-1]
    IS     = period.income_statement
    BS     = period.balance_sheet
    shares = target_mkt.shares_outstanding

    if not shares:
        return {}

    implied: dict[str, float | None] = {}

    if medians.get("P/E") and IS.net_income and IS.net_income > 0:
        implied["P/E"] = round(medians["P/E"] * IS.net_income / shares, 2)  # type: ignore[operator]

    if medians.get("EV/Sales") and IS.revenue:
        ev_implied = medians["EV/Sales"] * IS.revenue  # type: ignore[operator]
        equity = ev_implied - (BS.long_term_debt or 0.0) + (BS.cash or 0.0)
        implied["EV/Sales"] = round(equity / shares, 2)

    if medians.get("P/S") and IS.revenue:
        implied["P/S"] = round(medians["P/S"] * IS.revenue / shares, 2)  # type: ignore[operator]

    if medians.get("P/B") and BS.total_equity and BS.total_equity > 0:
        implied["P/B"] = round(medians["P/B"] * BS.total_equity / shares, 2)  # type: ignore[operator]

    return implied


def _value_band(implied: dict[str, float | None]) -> dict:
    vals = [v for v in implied.values() if v is not None]
    if not vals:
        return {}
    return {
        "low":  round(min(vals), 2),
        "mid":  round(statistics.mean(vals), 2),
        "high": round(max(vals), 2),
    }


# ---------------------------------------------------------------------------
# Path A — peer-based comps
# ---------------------------------------------------------------------------

def peer_comps(
    target_fin: HistoricalFinancials,
    target_mkt: MarketData,
    peers: list[tuple[str, HistoricalFinancials, MarketData]],
    dropped: list[dict],
) -> dict:
    """peers: already-resolved (ticker, financials, market_data) triples. dropped: peers
    the caller couldn't resolve (missing research data), pre-populated by the caller."""
    peer_results: list[dict] = []

    for peer_ticker, peer_fin, peer_mkt in peers:
        try:
            result = _compute_multiples(peer_fin, peer_mkt)
            result["ticker"] = peer_ticker
            peer_results.append(result)
        except Exception as exc:
            dropped.append({"ticker": peer_ticker, "reason": str(exc)})

    if not peer_results:
        return {"error": "No valid peers — all dropped", "dropped_peers": dropped}

    medians  = _median_multiples(peer_results)
    implied  = _implied_per_share(target_fin, target_mkt, medians)
    target_m = _compute_multiples(target_fin, target_mkt)

    return {
        "source":                  "peer comparables",
        "peers_used":              [p["ticker"] for p in peer_results],
        "dropped_peers":           dropped,
        "peer_median_multiples":   medians,
        "target_multiples":        target_m["multiples"],
        "implied_value_per_share": implied,
        "value_band":              _value_band(implied),
        "current_price":           target_mkt.current_price,
        "notes":                   target_m["notes"],
    }


# ---------------------------------------------------------------------------
# Path B — Damodaran sector fallback
# ---------------------------------------------------------------------------

def resolve_damodaran_industry(fin: HistoricalFinancials) -> tuple[str | None, list[str]]:
    """Map a company's SIC code to a Damodaran industry name. Returns (industry, notes) —
    industry is None when SIC is missing or unmapped (notes explain why)."""
    sic: int | None = getattr(fin.metadata, "sic", None)
    if sic is None:
        return None, ["CompanyMetadata.sic not available — add field to schema.py"]

    notes: list[str] = []
    if _is_financial(sic):
        notes.append(
            "Financial-sector ticker: EV/Sales not meaningful. "
            "P/S implied value provided as reference only. "
            "Consider dividend discount or excess-return model."
        )

    industry = _damodaran_industry(sic)
    if industry is None:
        notes.append(f"SIC {sic} unmapped — extend sic.csv")
    return industry, notes


def damodaran_fallback(
    fin: HistoricalFinancials,
    mkt: MarketData,
    industry: str,
    notes: list[str],
    sector_multiples: dict,
) -> dict:
    """industry/notes come from resolve_damodaran_industry(); sector_multiples is the
    already-resolved {"ev_sales", "price_sales", "trailing_pe"} dict for that industry."""
    sector_ev_sales  = sector_multiples["ev_sales"]
    sector_ps        = sector_multiples["price_sales"]
    sector_pe        = sector_multiples["trailing_pe"]

    period = fin.periods[-1]
    IS     = period.income_statement
    BS     = period.balance_sheet
    shares = mkt.shares_outstanding

    if not shares:
        return {"error": "shares_outstanding unavailable", "notes": notes}

    implied: dict[str, float | None] = {}

    if sector_ev_sales and IS.revenue:
        ev_implied = sector_ev_sales * IS.revenue
        equity = ev_implied - (BS.long_term_debt or 0.0) + (BS.cash or 0.0)
        implied["EV/Sales (sector)"] = round(equity / shares, 2)

    if sector_ps and IS.revenue:
        implied["P/S (sector)"] = round(sector_ps * IS.revenue / shares, 2)

    if sector_pe and IS.net_income and IS.net_income > 0:
        implied["P/E (sector)"] = round(sector_pe * IS.net_income / shares, 2)

    return {
        "source":   "Damodaran sector median",
        "industry": industry,
        "sector_multiples": {
            "EV/Sales":    sector_ev_sales,
            "P/S":         sector_ps,
            "Trailing PE": sector_pe,
        },
        "implied_value_per_share": implied,
        "value_band":              _value_band(implied),
        "current_price":           mkt.current_price,
        "notes":                   notes,
    }
