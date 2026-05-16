from datetime import date
import warnings
from pydantic import (
    BaseModel, 
    computed_field, 
    model_validator,
    ConfigDict,
)
import pandas as pd


class CompanyMetadata(BaseModel):
    ticker: str
    cik: str
    name: str

    sic: str | None = None
    industry: str | None = None              # this IS the SIC description

    fiscal_year_end: str | None = None
    entity_type: str | None = None
    filer_category: str | None = None
    state_of_incorporation: str | None = None

    website: str | None = None
    phone: str | None = None


class PerShare(BaseModel):
    basic_shares:                       float | None = None
    diluted_shares:                     float | None = None   


class IncomeStatement(BaseModel):
    # period: Period   # ← add ` | None = None`

    revenue:                            float | None = None
    cogs:                               float | None = None
    gross_profit:                       float | None = None
    ebit:                               float | None = None     # = EBIT
    tax_expense:                        float | None = None     # for NOPAT = EBIT * (1 - tax_rate)
    net_income:                         float | None = None     # sanity check

    @model_validator(mode="after")
    def fill_gross_profit(self):
        if self.gross_profit is None and self.revenue and self.cogs:
            self.gross_profit = self.revenue - self.cogs
        return self

    @model_validator(mode="after")
    def check_gross_profit(self):
        if all(v is not None for v in [self.revenue, self.cogs, self.gross_profit]):
            diff = abs((self.revenue - self.cogs) - self.gross_profit)
            if diff > self.revenue * 0.01:
                warnings.warn(f"Gross profit mismatch: diff {diff:,.0f}")
        return self

    @model_validator(mode="after")
    def check_tax_rate(self):
        if self.ebit is not None and self.tax_expense is not None and self.ebit != 0:
            effective_rate = self.tax_expense / self.ebit
            if not (0 < effective_rate < 0.6):
                warnings.warn(f"Unusual tax rate: {effective_rate:.1%}")
        return self

    @computed_field
    @property
    def ebiat(self) -> float | None:
        if self.ebit is not None and self.tax_expense is not None:
            return self.ebit - self.tax_expense
        return None

class BalanceSheet(BaseModel):
    total_current_assets:               float | None = None
    cash:                               float | None = None
    total_assets:                       float | None = None
    total_current_liabilities:          float | None = None    
    total_liabilities:                  float | None = None
    total_equity:                       float | None = None

    @computed_field
    @property
    def net_working_capital(self) -> float | None:
        if self.total_current_assets is not None and self.total_current_liabilities is not None:
            return self.total_current_assets - self.total_current_liabilities
        return None
        
    @model_validator(mode="after")
    def fill_total_liabilities(self):
        if self.total_liabilities is None and self.total_assets is not None and self.total_equity is not None:
            self.total_liabilities = self.total_assets - self.total_equity
        return self

    @model_validator(mode="after")
    def check_balance_sheet_identity(self):
        if all(v is not None for v in [
            self.total_assets, self.total_liabilities, self.total_equity
        ]):
            diff = abs(self.total_assets - (self.total_liabilities + self.total_equity))
            tolerance = self.total_assets * 0.01
            if diff > tolerance:
                warnings.warn(
                    f"Balance sheet gap: {diff:,.0f} "
                    f"({diff/self.total_assets:.1%} of assets)"
                )
        return self
    

class CashFlowStatement(BaseModel):
    # model_config = ConfigDict(extra="allow")
    net_income:                         float | None = None
    capex:                              float | None = None
    depreciation_amortization:          float | None = None
    cfo:                                float | None = None


    @computed_field
    @property
    def fcf(self) -> float | None:
        """FCF = CFO - CapEx (primary). Falls back to EBIAT method if CFO missing."""
        if self.cfo is not None and self.capex is not None:
            return self.cfo - self.capex
        return None
    

class MarketData(BaseModel):
    ticker:               str
    current_price:        float | None = None
    beta:                 float | None = None
    shares_outstanding:   float | None = None
    market_cap:           float | None = None
    risk_free_rate:       float | None = None  # from FRED DGS10
    

class HistoricalFinancials(BaseModel):
    ticker: str
    metadata: CompanyMetadata
    per_share: dict[str, PerShare]
    income_statements: dict[str, IncomeStatement]
    balance_sheets: dict[str, BalanceSheet]
    cash_flows: dict[str, CashFlowStatement]

    _SECTIONS = {
        "per_share": "per_share",
        "income":    "income_statements",
        "balance":   "balance_sheets",
        "cash_flow": "cash_flows",
    }

    @model_validator(mode="after")
    def check_net_income_reconciliation(self):
        for period in self.income_statements:
            if period not in self.cash_flows:
                continue
            is_ = self.income_statements[period]
            cfs = self.cash_flows[period]
            if is_.net_income is not None and cfs.net_income is not None:
                diff = abs(is_.net_income - cfs.net_income)
                if diff > abs(is_.net_income) * 0.01:
                    warnings.warn(
                        f"[{period}] Net income mismatch IS vs CFS: "
                        f"IS={is_.net_income:,.0f} CFS={cfs.net_income:,.0f} "
                        f"diff={diff:,.0f}"
                    )
        return self
    
    def to_dataframe(self, statement: str) -> pd.DataFrame:
        """Wide DataFrame — rows = periods (asc), cols = line items."""
        if statement not in self._SECTIONS:
            raise ValueError(f"Unknown statement: {statement}. "
                            f"Pick from {list(self._SECTIONS)}")

        section = getattr(self, self._SECTIONS[statement])
        df = pd.DataFrame({p: m.model_dump() for p, m in section.items()}).T
        df.index = pd.to_datetime(df.index)
        df.index.name = "period"
        return df.sort_index()