"""Merge rules for writing into research_messages.

Only financials needs real merge logic — its fetches can be non-overlapping
(span=N today, an explicit older fiscal_years list tomorrow), so a later
fetch must never drop periods or fields an earlier fetch already established.
Every other research tool (market_data, sector_data, damodaran_sector) is a
plain single-snapshot replace via upsert() with no `merge` argument — there's
no partial-overlap case for them.
"""

from __future__ import annotations

from typing import Any


def merge_financials_data(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Union periods by fiscal_year (new wins per overlapping year).

    Metadata fields are coalesced — a fetch returning a null field (e.g. a
    flaky source) never blanks out a previously known value.
    """
    old_periods = {p["fiscal_year"]: p for p in old.get("periods", [])}
    new_periods = {p["fiscal_year"]: p for p in new.get("periods", [])}
    merged_periods = {**old_periods, **new_periods}

    old_meta = old.get("metadata") or {}
    new_meta = new.get("metadata") or {}
    merged_meta = {
        key: new_meta.get(key) if new_meta.get(key) is not None else old_meta.get(key)
        for key in {**old_meta, **new_meta}
    }

    return {
        "ticker": new.get("ticker", old.get("ticker")),
        "metadata": merged_meta,
        "periods": [merged_periods[k] for k in sorted(merged_periods)],
    }
