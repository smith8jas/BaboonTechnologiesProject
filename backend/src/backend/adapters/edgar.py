from edgar import Company, set_identity
from edgar.xbrl import XBRLS
from backend.core.config import settings

STATEMENT_TYPES = {
    "income_statement": "IncomeStatement",
    "balance_sheet":    "BalanceSheet",
    "cash_flow":        "CashFlowStatement",
}


class Edgar(Company):
    """edgartools Company wrapper; exposes period-first statement fetchers."""

    def __init__(self, ticker: str):
        set_identity(settings.edgar_user_agent)
        super().__init__(ticker)
        self._xbrls_cache: dict[int, XBRLS] = {}

    def xbrls(self, span: int = 3) -> XBRLS:
        if span not in self._xbrls_cache:
            filings = self.get_filings(form="10-K", amendments=False)
            self._xbrls_cache[span] = XBRLS.from_filings(filings[:span])
        return self._xbrls_cache[span]

    def fetch_statement(self, statement: str, span: int = 3) -> dict[str, dict]:
        """Return {period_end: {standard_concept: numeric_value}}."""
        if statement not in STATEMENT_TYPES:
            raise ValueError(f"Unknown statement: {statement}")

        df = (
            self.xbrls(span).facts.query().to_dataframe()
            .pipe(lambda d: d[d["statement_type"] == STATEMENT_TYPES[statement]])
            .pipe(lambda d: d[d["standard_concept"].notna()])
            .pipe(lambda d: d[~d["is_abstract"]])
            .sort_values(["is_total", "level"], ascending=[False, True])
            .drop_duplicates(subset=["standard_concept", "period_end"], keep="first")
        )

        out: dict[str, dict] = {}
        for _, row in df.iterrows():
            out.setdefault(row["period_end"], {})[row["standard_concept"]] = row["numeric_value"]
        return out

    def metadata(self) -> dict:
        data = getattr(self, "data", None)
        addr = self.business_address() if callable(getattr(self, "business_address", None)) else None

        return {
            # Identity
            "ticker": self.tickers[0] if self.tickers else "",
            "cik":    str(self.cik),
            "name":   self.name,
            "former_names": list(getattr(data, "former_names", []) or []),

            # Classification — `industry` already IS the SIC description in edgartools
            "sic":             str(getattr(self, "sic", "") or "") or None,
            "industry":        getattr(self, "industry", None),

            # Filing context
            "fiscal_year_end":         getattr(self, "fiscal_year_end", None),
            "entity_type":             getattr(data, "entity_type", None),
            "filer_category":          getattr(data, "category", None),
            "state_of_incorporation":  getattr(data, "state_of_incorporation", None),

            # Contact
            "website": getattr(self, "website", None),
            "phone":   getattr(addr, "phone", None) if addr else None,
        }

    def fetch_all(self, span: int = 3) -> dict[str, dict]:
        return {name: self.fetch_statement(name, span) for name in STATEMENT_TYPES}