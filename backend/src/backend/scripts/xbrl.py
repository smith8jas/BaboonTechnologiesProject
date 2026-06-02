"""
Utility: look up XBRL concepts that map to a given standard tag.

Usage:
    uv run python -m backend.scripts.xbrl_lookup InterestExpense
    uv run python -m backend.scripts.xbrl_lookup Revenue
"""

import sys
import json
import urllib.request
from functools import lru_cache
from backend.adapters.edgar import Edgar

URL = "https://raw.githubusercontent.com/dgunning/edgartools/refs/heads/main/edgar/xbrl/standardization/gaap_mappings.json"


@lru_cache(maxsize=1)
def _load() -> dict:
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    return json.loads(urllib.request.urlopen(req).read())


def find_xbrl_concepts(standard_tag: str) -> list[dict]:
    """
    Return all XBRL concepts that map to the given standard tag.
    Sorted by confidence desc, then company_count desc.
    """
    data = _load()
    results = []
    for xbrl_concept, meta in data.items():
        tags = meta.get("standard_tags", [])
        if standard_tag in tags:
            results.append({
                "xbrl_concept":   xbrl_concept,
                "confidence":     meta.get("confidence"),
                "company_count":  meta.get("company_count", 0),
                "statement":      meta.get("statement"),
                "display_name":   meta.get("display_name"),
            })
    return sorted(
        results,
        key=lambda x: (x["confidence"] or 0, x["company_count"] or 0),
        reverse=True,
    )


def main():
    # if len(sys.argv) < 2:
    #     sys.exit("Usage: xbrl_lookup.py <StandardTag>  e.g. InterestExpense")

    # tag = sys.argv[1]
    # results = find_xbrl_concepts(tag)

    # if not results:
    #     print(f"No XBRL concepts found mapping to '{tag}'")
    #     return

    # print(f"\nXBRL concepts → '{tag}'  ({len(results)} found)\n")
    # print(f"  {'Concept':<60} {'Conf':>6}  {'Companies':>10}  Statement")
    # print(f"  {'-'*60}  {'-'*6}  {'-'*10}  {'-'*20}")
    # for r in results:
    #     conf = f"{r['confidence']:.3f}" if r["confidence"] is not None else "  n/a"
    #     print(
    #         f"  {r['xbrl_concept']:<60} {conf:>6}  "
    #         f"{(r['company_count'] or 0):>10,}  {r['statement'] or ''}"
    #     )

    company = Edgar("AAPL")
    df = company.xbrls(5).facts.query().to_dataframe()
    result = df[df["standard_concept"] == "InterestExpense"][["standard_concept", "statement_type", "period_end"]].drop_duplicates()
    print(result)

if __name__ == "__main__":
    main()