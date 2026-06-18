"""Catalog builder and retention over the in-state research/calculated message lists.

build_data_catalog -- lightweight availability summary for plan/react (unchanged shape).
purge               -- retention helper called by router every few cycles.

There is no payload builder here. response_node reads research_messages /
calculated_messages directly — each entry's `data` is already the full
content a tool returned, so nothing needs to be reconstructed for it.
"""

from __future__ import annotations

from typing import Any, Callable

from .store import find

# Identifier kinds that live in research_messages but are never surfaced in the
# catalog — internal inputs to other tools, not something a user asks about.
_INTERNAL_RESEARCH_KINDS = {"sector_data", "damodaran_sector"}

FETCHED_KEEP = 3       # cycles of research data to retain (costly to refetch)
CALCULATED_KEEP = 2    # cycles of calculated data to retain (free to regenerate)


def _catalog_fact_entry(entry: dict[str, Any]) -> dict[str, Any]:
    from ..tools import TOOLS_BY_NAME  # local import — avoids cache <-> tools import cycle

    kind = entry["identifier"][0]
    tool = TOOLS_BY_NAME.get(entry["tool"])
    description_lines = (getattr(tool, "description", "") or "").strip().splitlines()
    static_text = description_lines[0] if description_lines else entry["tool"]

    builder = _CATALOG_FACT_BUILDERS.get(kind)
    fact = dict(builder(entry["data"])) if builder else {}
    detail = fact.pop("detail", "")
    return {
        "available": True,
        **fact,
        "summary": f"{static_text} — {detail}" if detail else static_text,
    }


def _financials_fact(data: dict[str, Any]) -> dict[str, Any]:
    fiscal_years = [p.get("fiscal_year") for p in data.get("periods", [])]
    detail = f"{fiscal_years[0]}–{fiscal_years[-1]} ({len(fiscal_years)} periods)" if fiscal_years else ""
    return {"fiscal_years": fiscal_years, "max_span": len(fiscal_years), "detail": detail}


def _market_data_fact(data: dict[str, Any]) -> dict[str, Any]:
    return {"include_rfr": data.get("risk_free_rate") is not None}


def _period_keyed_fact(data: dict[str, Any]) -> dict[str, Any]:
    """Shared shape for ratios/growth — one sub-dict per fiscal year."""
    span = len(data)
    return {"span": span, "detail": f"{span} periods" if span else ""}


def _dcf_fact(data: dict[str, Any]) -> dict[str, Any]:
    iv = data.get("intrinsic_value_per_share")
    wacc = data.get("wacc")
    detail = ""
    if iv is not None:
        wacc_str = f"{wacc:.1%}" if wacc is not None else "N/A"
        detail = f"base FY={data.get('fiscal_year')}, WACC={wacc_str}, intrinsic value=${iv:.2f}/share"
    return {"base_fiscal_year": data.get("fiscal_year"), "detail": detail}


def _comparables_fact(data: dict[str, Any]) -> dict[str, Any]:
    band = data.get("value_band") or {}
    low, high = band.get("low"), band.get("high")
    detail = f"implied value band ${low:.2f}–${high:.2f}/share" if low is not None and high is not None else ""
    return {"detail": detail}


_CATALOG_FACT_BUILDERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "financials": _financials_fact,
    "market_data": _market_data_fact,
    "ratios": _period_keyed_fact,
    "growth": _period_keyed_fact,
    "dcf": _dcf_fact,
    "comparables": _comparables_fact,
}


def _all_tickers(research_messages: list[dict], calculated_messages: list[dict]) -> list[str]:
    tickers = {e["ticker"] for e in research_messages if e["ticker"]}
    tickers |= {e["ticker"] for e in calculated_messages if e["ticker"]}
    return sorted(tickers)


def build_data_catalog(research_messages: list[dict], calculated_messages: list[dict]) -> dict:
    """Build a compact availability summary for plan/react prompts."""
    catalog: dict = {"companies": [], "global": {"sector_data_years": []}}

    for ticker in _all_tickers(research_messages, calculated_messages):
        fin = find(research_messages, ("financials", ticker))
        name = (fin["data"].get("metadata") or {}).get("name") if fin else None
        company: dict = {"ticker": ticker, "name": name, "searched": {}, "calculated": {}}

        for entry in research_messages:
            kind = entry["identifier"][0]
            if entry["ticker"] != ticker or kind in _INTERNAL_RESEARCH_KINDS:
                continue
            company["searched"][kind] = _catalog_fact_entry(entry)

        for entry in calculated_messages:
            if entry["ticker"] != ticker:
                continue
            identifier = entry["identifier"]
            kind = identifier[0]
            fact = _catalog_fact_entry(entry)
            if len(identifier) > 2:
                company["calculated"].setdefault(kind, {})[identifier[2]] = fact
            else:
                company["calculated"][kind] = fact

        catalog["companies"].append(company)

    catalog["global"]["sector_data_years"] = sorted(
        e["identifier"][1] for e in research_messages if e["identifier"][0] == "sector_data"
    )
    return catalog


def purge(
    research_messages: list[dict], calculated_messages: list[dict], current_cycle: int
) -> tuple[list[dict], list[dict]]:
    """Drop entries older than their retention window. Calculated data is purged more
    aggressively than research data since recomputing it is free."""
    fetched_threshold = current_cycle - FETCHED_KEEP
    calculated_threshold = current_cycle - CALCULATED_KEEP

    new_research = research_messages
    if fetched_threshold >= 1:
        new_research = [e for e in research_messages if e["cycle"] > fetched_threshold]

    new_calculated = calculated_messages
    if calculated_threshold >= 1:
        new_calculated = [e for e in calculated_messages if e["cycle"] > calculated_threshold]

    return new_research, new_calculated
