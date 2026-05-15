from backend.adapters.edgar import Edgar
from edgar.xbrl import XBRLS
from edgar import *
import sys
from backend.core.config import settings
import pandas as pd
import json
from backend.processing.xbrl_map import (
    PS_MAPPINGS, 
    IS_MAPPINGS, 
    BS_MAPPINGS, 
    CFS_MAPPINGS,
)
from backend.processing.schema import (
    Period, 
    PerShare,
    IncomeStatement,
    BalanceSheet,
    CashFlowStatement,
    HistoricalFinancials,
)


def main():
    set_identity(settings.edgar_user_agent)

    if len(sys.argv) != 2:
        print("Usage: uv run test.py <ticker>")
        sys.exit(1)

    TICKER = sys.argv[1].upper()

    xbrls = get_xbrls(TICKER)

    df = xbrls.facts.query().to_dataframe()
    print(df[df["standard_concept"] == "Revenue"][["concept", "fiscal_year", "period_end", "numeric_value"]].to_string())

    mapped_ps = map_all_periods(to_period_first(preprocess(xbrls, "income_statement")), PS_MAPPINGS)
    mapped_is = map_all_periods(to_period_first(preprocess(xbrls, "income_statement")), IS_MAPPINGS)
    mapped_bs = map_all_periods(to_period_first(preprocess(xbrls, "balance_sheet")),    BS_MAPPINGS)
    mapped_cf = map_all_periods(to_period_first(preprocess(xbrls, "cash_flow")),        CFS_MAPPINGS)

    # ── Instantiate ───────────────────────────────────────────
    per_share         = {p: PerShare(**mapped_ps[p]) for p in mapped_ps}
    income_statements = {p: IncomeStatement(**mapped_is[p]) for p in mapped_is}
    balance_sheets    = {p: BalanceSheet(**mapped_bs[p]) for p in mapped_bs}
    cash_flows        = {p: CashFlowStatement(**mapped_cf[p]) for p in mapped_cf}

    # ── HistoricalFinancials ──────────────────────────────────
    hf = HistoricalFinancials(
        ticker=TICKER,
        per_share=per_share,
        income_statements=income_statements,
        balance_sheets=balance_sheets,
        cash_flows=cash_flows,
    )

    # ── Print ─────────────────────────────────────────────────
    print(f"\n{'='*50}")
    print(f"  {TICKER} — Historical Financials")
    print(f"{'='*50}")

    for period in sorted(hf.per_share):
        print(f"\n── Per Share Data [{period}] ──")
        print(hf.per_share[period].model_dump_json(indent=2))

    for period in sorted(hf.income_statements):
        print(f"\n── Income Statement [{period}] ──")
        print(hf.income_statements[period].model_dump_json(indent=2))

    for period in sorted(hf.balance_sheets):
        print(f"\n── Balance Sheet [{period}] ──")
        print(hf.balance_sheets[period].model_dump_json(indent=2))

    for period in sorted(hf.cash_flows):
        print(f"\n── Cash Flow [{period}] ──")
        print(hf.cash_flows[period].model_dump_json(indent=2))


def get_xbrls(ticker: str, historical_span: int = 3) -> XBRLS:
    filings = Company(ticker).get_filings(form="10-K", amendments=False)
    return XBRLS.from_filings(filings[:historical_span])


def preprocess(xbrls: XBRLS, statement: str) -> dict:
    statement_map = {
        "income_statement": "IncomeStatement",
        "balance_sheet":    "BalanceSheet",
        "cash_flow":        "CashFlowStatement",
    }

    df = (xbrls.facts.query()
        .to_dataframe()
        .pipe(lambda d: d[d["statement_type"] == statement_map[statement]])
        .pipe(lambda d: d[d["standard_concept"].notna()])
        .pipe(lambda d: d[~d["is_abstract"]])
        .sort_values(["is_total", "level"], ascending=[False, True])
        .drop_duplicates(subset=["standard_concept", "period_end"], keep="first")
    )

    return (
        df.groupby("standard_concept")
        .apply(lambda x: dict(zip(x["period_end"], x["numeric_value"])))
        .to_dict()
    )


def extract_period(data: dict, period: str) -> dict:
    return {
        concept: values[period]
        for concept, values in data.items()
        if period in values
    }


def to_schema(data: dict, period: str, xbrl_mappings: dict) -> dict:
    reverse_map = {v: k for k, v in xbrl_mappings.items()}
    row = extract_period(data, period)
    return {reverse_map[k]: v for k, v in row.items() if k in reverse_map}


def to_period_first(data: dict) -> dict[str, dict]:
    """{concept: {period: value}} → {period: {concept: value}}"""
    out = {}
    for concept, periods in data.items():
        for period, value in periods.items():
            out.setdefault(period, {})[concept] = value
    return out


def map_keys(row: dict, mappings: dict) -> dict:
    reverse = {}
    for k, v in mappings.items():
        if isinstance(v, list):
            for concept in v:
                reverse[concept] = k
        else:
            reverse[v] = k

    mapped = {}
    for internal_key in set(reverse.values()):
        # find first non-null match in priority order
        candidates = [c for c, k in reverse.items() if k == internal_key]
        for candidate in candidates:
            if candidate in row and row[candidate] is not None:
                mapped[internal_key] = row[candidate]
                break

    # dropped = {k: v for k, v in row.items() if k not in reverse}
    # print(f"Dropped: {json.dumps(dropped, indent=2)}")
    return mapped


def map_all_periods(by_period: dict, mappings: dict) -> dict:
    """Apply map_keys to every period."""
    return {period: map_keys(row, mappings) for period, row in by_period.items()}

if __name__ == "__main__":
    main()