from backend.adapters.edgar import Edgar
from edgar.xbrl import XBRLS
from edgar import *
from backend.core.config import settings
from backend.processing.schema import MarketData


def main()
    ...


def build_market_data(ticker: str) -> MarketData:
    yahoo = fetch_yahoo_market(ticker)   # price, beta, shares, market_cap
    rfr   = fetch_risk_free_rate()       # FRED DGS10

    return MarketData(
        ticker=ticker,
        current_price=yahoo["current_price"],
        beta=yahoo["beta"],
        shares_outstanding=yahoo["shares_outstanding"],
        market_cap=yahoo["market_cap"],
        risk_free_rate=rfr,
    )


if __name__ == "__main__":
    main()