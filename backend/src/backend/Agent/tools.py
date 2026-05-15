from langchain_core.tools import tool

from backend.adapters.edgar import Edgar
from backend.adapters.fred import fetch_risk_free_rate
from backend.adapters.yahoo_finance import fetch_yahoo_market

@tool
def get_company_cik(ticker: str) -> str:
    """Resolve a company stock ticker to its SEC CIK identifier."""
    return Edgar(ticker).resolve_cik()

@tool
def get_risk_free_rate() -> float:
    """Fetch the latest 10-year Treasury risk-free rate from FRED."""
    return fetch_risk_free_rate()

@tool
def get_market_data(ticker: str) -> dict:
    """Fetch current market data for a public company by stock ticker."""
    return fetch_yahoo_market(ticker)
   

tools = [get_company_cik, get_risk_free_rate, get_market_data]

