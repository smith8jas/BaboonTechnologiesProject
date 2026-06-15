import os
from pathlib import Path

import pandas as pd
from backend.core.config import settings

from edgar import set_identity, use_local_storage, download_edgar_data
from edgar.reference import get_companies_by_industry


EDGAR_DATA_DIR = Path(os.getenv("EDGAR_DATA_DIR", "./data/edgar"))
PEER_TABLE_PATH = Path("./data/sic_peers.parquet")  # committed artifact, MBs


def configure_edgar() -> None:
    EDGAR_DATA_DIR.mkdir(parents=True, exist_ok=True)
    use_local_storage(str(EDGAR_DATA_DIR))
    set_identity(settings.edgar_user_agent)


def download_reference_data() -> None:
    """
    Maintainer-only, one-time. ~500 MB submissions download needed because
    get_companies_by_industry() reads the submissions store.
    Teammates never run this — they read the committed parquet.
    """
    configure_edgar()
    download_edgar_data(submissions=True, facts=False, reference=True)


def build_peer_table() -> pd.DataFrame:
    """
    Maintainer-only. Materializes the SIC->company mapping to a small file
    the team commits and reads. Teammates never run the bulk download.
    """
    configure_edgar()
    df = get_companies_by_industry()  # full reference table
    PEER_TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PEER_TABLE_PATH, index=False)
    return df


def get_industry_peers(sic_code: int) -> pd.DataFrame:
    """
    Team-facing lookup. Reads the committed artifact — no download.
    """
    if not PEER_TABLE_PATH.exists():
        raise FileNotFoundError(
            f"{PEER_TABLE_PATH} missing. A maintainer must run build_peer_table()."
        )
    df = pd.read_parquet(PEER_TABLE_PATH)
    return df[df["sic"] == sic_code]


if __name__ == "__main__":
    # Maintainer one-time setup:
    download_reference_data()
    build_peer_table()

    # Team usage:
    print(get_industry_peers(7372).head())