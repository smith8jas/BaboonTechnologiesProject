"""
Confirms the whitelist fallback fix is a no-op for clean tickers.

Usage:
    uv run python -m backend.scripts.depreciation_impact
"""

from backend.adapters.edgar import Edgar

FALLBACK = {
    "DepreciationAmortizationAndOther",
    "DepreciationAmortizationAndImpairment",
}

TICKERS = ["AAPL", "WMT", "XOM", "MSFT", "TSLA"]


def main():
    print(f"\n{'Ticker':<8} {'total_nan':>10} {'promotable':>12}  concepts")
    print(f"{'─'*8}  {'─'*10}  {'─'*12}  {'─'*40}")

    for ticker in TICKERS:
        df = Edgar(ticker).xbrls(5).facts.query().to_dataframe()
        df = df[~df["is_abstract"]]

        nan_rows = df[df["standard_concept"].isna()]

        def strip_prefix(concept: str) -> str:
            return concept.split("_", 1)[1] if "_" in concept else concept

        stripped = nan_rows["concept"].apply(strip_prefix)
        promotable = nan_rows[stripped.isin(FALLBACK)]
        concepts = list(stripped[stripped.isin(FALLBACK)].unique())

        print(f"{ticker:<8} {len(nan_rows):>10,} {len(promotable):>12,}  {concepts}")


if __name__ == "__main__":
    main()