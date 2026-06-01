import pandas as pd
from functools import lru_cache

MRP_URL = "https://www.stern.nyu.edu/~adamodar/pc/datasets/histimpl.xls"

@lru_cache(maxsize=1)
def fetch_equity_risk_premium(year: int | None = None) -> float | None:
    try:
        df = pd.read_excel(MRP_URL, skiprows=6, index_col="Year")
        df = df[pd.to_numeric(df.index, errors='coerce').notna()]
        df.index = df.index.astype(int)
    except Exception:
        return None
    if year is None or year not in df.index:
        year = df.index.max()        # latest available
    return float(df.loc[year, "Implied ERP (FCFE)"])