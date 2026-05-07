from backend.core.config import settings
import requests


class Edgar():
    _companies = None
    _headers = {"User-Agent": settings.edgar_user_agent}    

    def __init__(self, ticker):
        self.ticker = ticker
        if self._companies is None:
            self._companies = requests.get(
                "https://www.sec.gov/files/company_tickers.json", headers=self._headers
            ).json()

    def resolve_cik(self):
        for company in self._companies.values():
            if company["ticker"].lower() == self.ticker.lower():
                return str(company["cik_str"]).zfill(10)
        raise ValueError(f"Could not find cik for ticker: {self.ticker}")