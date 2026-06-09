import pandas as pd
from functools import lru_cache

MRP_URL = "https://www.stern.nyu.edu/~adamodar/pc/datasets/histimpl.xls"
PE_URL  = "https://www.stern.nyu.edu/~adamodar/pc/datasets/pedata.xls"
PS_URL  = "https://www.stern.nyu.edu/~adamodar/pc/datasets/psdata.xls"


@lru_cache(maxsize=1)
def fetch_equity_risk_premium(year: int | None = None) -> float:
    df = pd.read_excel(MRP_URL, skiprows=6, index_col="Year")
    df = df[pd.to_numeric(df.index, errors="coerce").notna()]
    df.index = df.index.astype(int)
    if year is None or year not in df.index:
        year = int(df.index.max())
    return float(df.loc[year, "Implied ERP (FCFE)"])


@lru_cache(maxsize=1)
def _load_pe_table() -> pd.DataFrame:
    df = pd.read_excel(PE_URL, sheet_name="Industry Averages", skiprows=7, index_col=0)
    df.index.name = "Industry Name"
    return df


@lru_cache(maxsize=1)
def _load_ps_table() -> pd.DataFrame:
    df = pd.read_excel(PS_URL, sheet_name="Industry Averages", skiprows=7, index_col=0)
    df.index.name = "Industry Name"
    return df


def fetch_trailing_pe(industry: str = "Total Market") -> float | None:
    try:
        return float(_load_pe_table().loc[industry, "Trailing PE"])
    except (KeyError, ValueError):
        return None


def fetch_ev_sales(industry: str = "Total Market") -> float | None:
    try:
        return float(_load_ps_table().loc[industry, "EV/Sales"])
    except (KeyError, ValueError):
        return None


def fetch_price_sales(industry: str = "Total Market") -> float | None:
    try:
        return float(_load_ps_table().loc[industry, "Price/Sales"])
    except (KeyError, ValueError):
        return None