import yfinance as yf


def fetch_yahoo_market(ticker: str) -> dict:
    """
    Fetch market data from Yahoo Finance.

    Args:
        ticker (str): Stock ticker symbol.

    Returns:
        dict: Market data including:
            - current_price
            - beta
            - shares_outstanding
            - market_cap
    """

    try:
        stock = yf.Ticker(ticker)

        info = stock.info

        return {
            "current_price": info.get("currentPrice"),
            "beta": info.get("beta"),
            "shares_outstanding": info.get("sharesOutstanding"),
            "market_cap": info.get("marketCap"),
        }

    except Exception as e:
        raise ValueError(
            f"Failed to fetch Yahoo Finance data for ticker '{ticker}': {e}"
        )
        
