from datetime import date
import warnings
from pydantic import (
    BaseModel, 
    computed_field, 
    model_validator,
    ConfigDict,
)


class Period(BaseModel):
    filing_date: date       # "FY" | "Q1" | "Q2" | "Q3" | "Q4"


class IncomeStatement(BaseModel):
    # period: Period   # ← add ` | None = None`

    revenue:                            float | None = None
    cogs:                               float | None = None
    gross_profit:                       float | None = None
    operating_income:                   float | None = None     # = EBIT
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
        if self.operating_income and self.tax_expense:
            effective_rate = self.tax_expense / self.operating_income
            if not (0 < effective_rate < 0.6):
                warnings.warn(f"Unusual tax rate: {effective_rate:.1%}")
        return self


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
        if self.total_current_assets and self.total_current_liabilities:
            return self.total_current_assets - self.total_current_liabilities
        return None
        
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


class HistoricalFinancials(BaseModel):
    ticker: str
    income_statements: dict[str, IncomeStatement]
    balance_sheets: dict[str, BalanceSheet]
    cash_flows: dict[str, CashFlowStatement]

    @model_validator(mode="after")
    def check_net_income_reconciliation(self):
        for period in self.income_statements:
            if period not in self.cash_flows:
                continue
            is_ = self.income_statements[period]
            cfs = self.cash_flows[period]
            if is_.net_income and cfs.net_income:
                diff = abs(is_.net_income - cfs.net_income)
                if diff > is_.net_income * 0.01:
                    warnings.warn(
                        f"[{period}] Net income mismatch IS vs CFS: "
                        f"IS={is_.net_income:,.0f} CFS={cfs.net_income:,.0f} "
                        f"diff={diff:,.0f}"
                    )
        return self
    
    @computed_field
    @property
    def fcf(self) -> float | None:
        """FCF = CFO - CapEx (primary). Falls back to EBIAT method if CFO missing."""
        if self.cfo is not None and self.capex is not None:
            return self.cfo - self.capex
        return None
