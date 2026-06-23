"""
Diagnostic: find depreciation XBRL concepts for a ticker.

Usage:
    uv run python -m backend.scripts.depreciation_lookup MSFT
    uv run python -m backend.scripts.depreciation_lookup TSLA
"""

import sys
import json
import urllib.request
from functools import lru_cache
from backend.adapters.edgar import Edgar

GAAP_MAPPINGS_URL = (
    "https://raw.githubusercontent.com/dgunning/edgartools/refs/heads/main"
    "/edgar/xbrl/standardization/gaap_mappings.json"
)

# Standard tags to probe — covers IS depreciation + CFS D&A
DEPRECIATION_TAGS = [
    "DepreciationAmortization",
    "Depreciation",
    "DepreciationAndAmortization",
]


@lru_cache(maxsize=1)
def _load_gaap_mappings() -> dict:
    req = urllib.request.Request(
        GAAP_MAPPINGS_URL, headers={"User-Agent": "Mozilla/5.0"}
    )
    return json.loads(urllib.request.urlopen(req).read())


def xbrl_concepts_for_tag(standard_tag: str) -> list[dict]:
    """All XBRL concepts that map to standard_tag, sorted by confidence desc."""
    data = _load_gaap_mappings()
    results = []
    for concept, meta in data.items():
        if standard_tag in meta.get("standard_tags", []):
            results.append(
                {
                    "xbrl_concept": concept,
                    "confidence": meta.get("confidence"),
                    "company_count": meta.get("company_count", 0),
                    "statement": meta.get("statement"),
                }
            )
    return sorted(
        results,
        key=lambda x: (x["confidence"] or 0, x["company_count"] or 0),
        reverse=True,
    )


def section(title: str) -> None:
    print(f"\n{'─' * 70}")
    print(f"  {title}")
    print(f"{'─' * 70}")


def main():
    ticker = sys.argv[-1] if len(sys.argv) >= 2 else "MSFT"

    # ── 1. What XBRL concepts exist in the gaap_mappings for depreciation ──
    section("Known XBRL concepts → depreciation standard tags")
    for tag in DEPRECIATION_TAGS:
        concepts = xbrl_concepts_for_tag(tag)
        print(f"\n  standard_tag = {tag}  ({len(concepts)} concepts)")
        print(f"  {'Concept':<60} {'Conf':>6}  {'Companies':>10}  Statement")
        print(f"  {'-'*60}  {'-'*6}  {'-'*10}  {'-'*20}")
        for r in concepts[:15]:  # top 15
            conf = f"{r['confidence']:.3f}" if r["confidence"] is not None else "   n/a"
            print(
                f"  {r['xbrl_concept']:<60} {conf:>6}  "
                f"{(r['company_count'] or 0):>10,}  {r['statement'] or ''}"
            )

    # ── 2. What concepts does THIS ticker actually file? ────────────────────
    section(f"{ticker} — raw XBRL facts containing 'depreci' or 'amort'")
    company = Edgar(ticker)
    df = company.xbrls(5).facts.query().to_dataframe()

    mask = df["standard_concept"].str.contains(
        "depreci|amort", case=False, na=False
    ) | df["concept"].str.contains(
        "depreci|amort", case=False, na=False
    )
    hits = (
        df[mask][["concept", "standard_concept", "statement_type", "period_end", "fiscal_period", "numeric_value"]]
        .query("fiscal_period == 'FY'")
        .drop_duplicates(subset=["concept", "standard_concept", "period_end"])
        .sort_values(["standard_concept", "period_end"])
    )

    if hits.empty:
        print(f"  No depreciation/amortization concepts found for {ticker}")
    else:
        print(hits.to_string(index=False))

    # ── 3. What does the raw fetch_all() return for these fields? ───────────
    section(f"{ticker} — raw fetch_all() cash_flow concepts (latest period)")
    raw = company.fetch_all(5)
    latest_key = sorted(raw["cash_flow"].keys())[-1]
    print(f"  Period: {latest_key}\n")
    for concept, value in sorted(raw["cash_flow"][latest_key].items()):
        if any(k in concept.lower() for k in ("deprec", "amort")):
            print(f"  {concept:<65} {value:>20,.0f}")

    section(f"{ticker} — raw fetch_all() income_statement concepts (latest period)")
    latest_is_key = sorted(raw["income_statement"].keys())[-1]
    print(f"  Period: {latest_is_key}\n")
    for concept, value in sorted(raw["income_statement"][latest_is_key].items()):
        if any(k in concept.lower() for k in ("deprec", "amort")):
            print(f"  {concept:<65} {value:>20,.0f}")

    # ── 4. What is in CFS_MAPPINGS for depreciation right now? ─────────────
    section("Current CFS_MAPPINGS depreciation entries")
    from backend.processing.xbrl_map import CFS_MAPPINGS, IS_MAPPINGS
    for field_name, concepts in CFS_MAPPINGS.items():
        if "deprec" in field_name.lower() or "amort" in field_name.lower():
            print(f"  {field_name}: {concepts}")
    for field_name, concepts in IS_MAPPINGS.items():
        if "deprec" in field_name.lower() or "amort" in field_name.lower():
            print(f"  IS/{field_name}: {concepts}")


if __name__ == "__main__":
    main()