from datetime import date
import warnings
from pydantic import (
    BaseModel,
    computed_field,
    field_validator,
    model_validator,
    ConfigDict,
)
import pandas as pd


class CompanyMetadata(BaseModel):
    cik: str
    name: str

    sic: int | None = None
    industry: str | None = None              # this IS the SIC description

    @field_validator("sic", mode="before")
    @classmethod
    def _coerce_sic(cls, v):
        if v is None:
            return None
        try:
            return int(v)
        except (ValueError, TypeError):
            return None

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
    revenue:                            float | None = None
    cogs:                               float | None = None
    gross_profit:                       float | None = None
    ebit:                               float | None = None     # = EBIT
    tax_expense:                        float | None = None     # for NOPAT = EBIT * (1 - tax_rate)
    net_income:                         float | None = None     # sanity check
    interest_expense:                   float | None = None
    depreciation_expense:               float | None = None

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

    @computed_field
    @property
    def ebitda(self) -> float | None:
        if self.ebit is not None and self.depreciation_expense is not None:
            return self.ebit + self.depreciation_expense
        return None


class BalanceSheet(BaseModel):
    total_current_assets:               float | None = None
    cash:                               float | None = None
    total_assets:                       float | None = None
    inventory:                          float | None = None
    accounts_receivable:                float | None = None
    accounts_payable:                   float | None = None
    short_term_debt:                    float | None = None
    long_term_debt:                     float | None = None
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
    interest_expense:                   float | None = None
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
    current_price:        float | None = None
    beta:                 float | None = None
    shares_outstanding:   float | None = None
    market_cap:           float | None = None
    risk_free_rate:       float | None = None       # from FRED DGS10


class SectorData(BaseModel):
    # industry: str | None = None
    equity_risk_premium: float | None = None
    long_term_growth_rate: float | None = 0.025     # Hardcoded at 2.5% (can change)


class FinancialPeriod(BaseModel):
    period_end: date
    fiscal_year: str | None = None        # ← add this
    income_statement: IncomeStatement
    balance_sheet: BalanceSheet
    cash_flow: CashFlowStatement
    per_share: PerShare

    @model_validator(mode="after")
    def check_net_income_reconciliation(self):
        ni_is = self.income_statement.net_income
        ni_cf = self.cash_flow.net_income
        if ni_is is not None and ni_cf is not None:
            diff = abs(ni_is - ni_cf)
            if diff > abs(ni_is) * 0.01:
                warnings.warn(
                    f"[{self.period_end}] NI mismatch IS vs CFS: "
                    f"IS={ni_is:,.0f} CFS={ni_cf:,.0f} diff={diff:,.0f}"
                )
        return self


class HistoricalFinancials(BaseModel):
    ticker: str
    metadata: CompanyMetadata
    periods: list[FinancialPeriod]   # sorted oldest → newest

    @model_validator(mode="after")
    def set_fiscal_years(self):
        fy_end = self.metadata.fiscal_year_end
        if fy_end:
            fy_month = int(fy_end[:2])
            for period in self.periods:
                year = period.period_end.year if fy_month >= 6 else period.period_end.year - 1
                period.fiscal_year = f"FY{year}"
        return self

    _SECTIONS = {
        "income":    "income_statement",
        "balance":   "balance_sheet",
        "cash_flow": "cash_flow",
        "per_share": "per_share",
    }

    def to_dataframe(self, statement: str) -> pd.DataFrame:
        """Wide DataFrame — rows = periods (asc), cols = line items."""
        if statement not in self._SECTIONS:
            raise ValueError(f"Unknown statement: {statement}. "
                            f"Pick from {list(self._SECTIONS)}")
        
        attr = self._SECTIONS[statement]
        df = pd.DataFrame({
            p.period_end: getattr(p, attr).model_dump()
            for p in self.periods
        }).T
        df.index = pd.to_datetime(df.index)
        df.index.name = "period"
        return df.sort_index()
    

class ValuationInputs(BaseModel):
    ticker:                         str
    risk_free_rate:                 float
    beta:                           float
    equity_risk_premium:            float               # Missing
    cost_of_debt:                   float               # Pre-tax
    market_cap:                     float
    shares_outstanding:             float
    total_debt:                     float
    tax_rate:                       float
    long_term_growth_rate:          float               # From industry growth (or GDP growth)
    projection_years:               int = 5
    falled_back_to_risk_free_rate:  bool = False

    @computed_field
    @property
    def cost_of_capital(self) -> float:
        return (self.risk_free_rate + self.beta * self.equity_risk_premium)
    
    @computed_field
    @property
    def wacc(self) -> float:
        w_e = self.market_cap / (self.market_cap + self.total_debt)
        w_d = self.total_debt / (self.market_cap + self.total_debt)
        return (self.cost_of_capital * w_e) + (self.cost_of_debt * (1 - self.tax_rate) * w_d)

    @model_validator(mode="after")
    def check_wacc(self):
        if self.wacc < self.long_term_growth_rate:
            warnings.warn(
                f"WACC ({self.wacc:.1%}) is below long-term growth rate "
                f"({self.long_term_growth_rate:.1%}) — terminal value will be negative."
            )
        return self
    

class Assumptions(BaseModel):
    revenue_growth:                                 float
    ebit_margin:                                    float
    tax_rate:                                       float
    depreciation_and_amortization_over_revenue:     float
    capex_over_revenue:                             float
    nwc_over_revenue:                               float


class DCFOutput(BaseModel):
    ticker:                         str
    fiscal_year:                    str
    projection_years:               list[str]    # projection years ["FY2026"...]
    intrinsic_value_per_share:      float
    terminal_value:                 float
    pv_terminal:                    float
    tv_pct_of_ev:                   float
    enterprise_value:               float
    projected_fcff:                 list[float]
    pv_fcff:                        list[float]
    projected_revenue:              list[float]
    projected_ebit:                 list[float]
    projected_ebiat:                list[float]
    projected_da:                   list[float]
    projected_capex:                list[float]
    projected_delta_nwc:            list[float]
    pv_factors:                     list[float]
    falled_back_to_risk_free_rate:  bool = False
