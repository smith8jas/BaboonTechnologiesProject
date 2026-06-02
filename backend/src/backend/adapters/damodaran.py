import pandas as pd
from functools import lru_cache

MRP_URL = "https://www.stern.nyu.edu/~adamodar/pc/datasets/histimpl.xls"

@lru_cache(maxsize=1)
def fetch_equity_risk_premium(year: int | None = None) -> float | None:
    try:
        df = pd.read_excel(MRP_URL, skiprows=6, index_col="Year")
    except Exception:
        return None
    df.index = pd.to_numeric(df.index, errors="coerce")
    df = df[df.index.notna()]
    df.index = df.index.astype(int)
    if year is None or year not in df.index:
        year = df.index.max()        # latest available
    return float(df.loc[year, "Implied ERP (FCFE)"])
