# Baboon Technologies — Architecture & Data Flow

> Work in progress. This document reflects the current state of the codebase as of May 2026.

---

## Table of Contents

1. [Overview](#overview)
2. [Directory Structure](#directory-structure)
3. [High-Level Data Flow](#high-level-data-flow)
4. [Layer-by-Layer Breakdown](#layer-by-layer-breakdown)
   - [Adapters (Data Sources)](#adapters-data-sources)
   - [XBRL Mapping](#xbrl-mapping)
   - [Schema & Validation](#schema--validation)
   - [Services (Orchestration)](#services-orchestration)
   - [Financial Ratios](#financial-ratios)
   - [Agent (LLM Interface)](#agent-llm-interface)
   - [API & CLI Harnesses](#api--cli-harnesses)
5. [Key Data Structures](#key-data-structures)
6. [Validation Logic](#validation-logic)
7. [Configuration & Environment](#configuration--environment)
8. [Testing](#testing)
9. [Work in Progress](#work-in-progress)

---

## Overview

Baboon Technologies is a **financial analysis platform** that:

1. Fetches structured financial statements from the SEC (EDGAR) for any publicly traded U.S. company.
2. Normalizes the raw XBRL data into validated Pydantic models (income statement, balance sheet, cash flow statement).
3. Enriches the data with real-time market data (Yahoo Finance) and macroeconomic indicators (FRED).
4. Exposes financial ratio calculations and (eventually) a DCF valuation engine.
5. Wraps everything in a LangGraph-powered AI agent that can answer investor questions using these tools.

**Tech stack:** Python ≥ 3.11, uv, FastAPI, LangChain/LangGraph, Pydantic v2, edgartools, yfinance, pandas.

---

## Directory Structure

```
BaboonTechnologiesProject/
├── ARCHITECTURE.md          ← this file
├── README.md
├── GitWorkflow.md
└── backend/
    ├── pyproject.toml       ← dependencies (uv)
    ├── .env / .env.example  ← secrets & config
    └── src/backend/
        ├── main.py          ← FastAPI entry point
        ├── core/
        │   ├── config.py    ← Pydantic Settings (reads .env)
        │   ├── llm.py       ← LangChain model initialization
        │   └── chat_bot.py  ← CLI chatbot loop
        ├── api/
        │   └── routes.py    ← HTTP endpoints
        ├── adapters/
        │   ├── edgar.py     ← SEC EDGAR API wrapper
        │   ├── yahoo_finance.py ← market data (price, beta, shares)
        │   └── fred.py      ← risk-free rate (10Y Treasury)
        ├── processing/
        │   ├── schema.py    ← Pydantic models + validation
        │   └── xbrl_map.py  ← XBRL concept → internal field mappings
        ├── services/
        │   ├── financials.py ← ETL orchestrator
        │   └── ratio.py     ← liquidity & solvency ratios
        ├── agent/
        │   ├── graph.py     ← LangGraph state machine
        │   ├── state.py     ← agent state TypedDict
        │   ├── tools.py     ← LangChain tools (CIK, RFR, market data)
        │   ├── prompts.py   ← system prompts
        │   └── memory.py    ← (WIP) agent memory structure
        └── scripts/
            ├── etl.py       ← CLI: human-readable output
            ├── etl_lean.py  ← CLI: JSON output
            ├── dcf_draft.py ← (WIP) DCF calculation skeleton
            └── dcf_variables.py ← (WIP) DCF inputs skeleton
```

---

## High-Level Data Flow

```
                          ┌──────────────────────────────────┐
                          │          User / Agent            │
                          │  (CLI script or LangGraph agent) │
                          └──────────────┬───────────────────┘
                                         │ ticker symbol
                                         ▼
                     ┌───────────────────────────────────────┐
                     │         services/financials.py        │
                     │      (ETL orchestrator + glue)        │
                     └────┬──────────────────────────────────┘
                          │
          ┌───────────────┼───────────────────────┐
          ▼               ▼                       ▼
  adapters/edgar.py  adapters/yahoo_finance.py  adapters/fred.py
  (SEC 10-K filings)  (price, beta, mkt cap)    (10Y T-rate)
          │
          │  raw {period_end: {xbrl_concept: value}}
          ▼
  processing/xbrl_map.py
  (map_keys / map_all_periods)
  4 mappings: IS / BS / CFS / PS
          │
          │  normalized {period_end: {internal_field: value}}
          ▼
  processing/schema.py  (Pydantic models)
  ┌─────────────────────────────────────┐
  │ IncomeStatement                     │
  │ BalanceSheet                        │  ← per fiscal period
  │ CashFlowStatement                   │
  │ PerShare                            │
  └──────────────┬──────────────────────┘
                 │  FinancialPeriod (one per fiscal year)
                 ▼
  HistoricalFinancials   +   MarketData
  (5 years of periods)       (current snapshot)
          │
          ▼
  services/ratio.py
  (liquidity & solvency ratios)
          │
          ▼
  Output: JSON / formatted CLI / agent response
```

---

## Layer-by-Layer Breakdown

### Adapters (Data Sources)

#### `adapters/edgar.py`

Wraps the `edgartools` library to pull SEC filings.

| Method | What it does |
|---|---|
| `__init__(ticker)` | Creates an `edgar.Company` instance with the configured user-agent email |
| `xbrls(span=3)` | Fetches the last `span` 10-K filings as XBRL objects (cached after first call) |
| `fetch_statement(statement, span)` | Returns `{period_end: {xbrl_concept: value}}` for one statement type |
| `metadata()` | Returns company info: CIK, name, industry, fiscal year end, state of incorporation |
| `fetch_all(span)` | Calls `fetch_statement` for all three statement types, returns combined dict |

**Deduplication logic inside `fetch_statement`:**
- When multiple XBRL facts exist for the same (concept, period_end) pair, the adapter keeps only one.
- Preference order: non-abstract > total-level concepts > line items.
- This prevents double-counting when EDGAR reports both a subtotal and its components.

#### `adapters/yahoo_finance.py`

Thin wrapper around `yfinance`. Returns a plain dict:

```python
{
  "current_price": float,
  "beta": float,
  "shares_outstanding": float,
  "market_cap": float
}
```

#### `adapters/fred.py`

Fetches the 10-year U.S. Treasury yield (`DGS10` series) from the Federal Reserve's FRED API. The result is **cached globally** after the first call so the API is not hit repeatedly within a single run.

---

### XBRL Mapping

**`processing/xbrl_map.py`**

The SEC's XBRL taxonomy uses verbose concept names (e.g., `"RevenueFromContractWithCustomerExcludingAssessedTax"`). This module maps ~285 such concepts to short internal field names used by the Pydantic schema.

Four mapping dictionaries:

| Dict | Target | # Concepts |
|---|---|---|
| `IS_MAPPINGS` | IncomeStatement fields | ~98 |
| `BS_MAPPINGS` | BalanceSheet fields | ~107 |
| `CFS_MAPPINGS` | CashFlowStatement fields | ~70 |
| `PS_MAPPINGS` | PerShare fields | ~12 |

**Multi-source fallback:** For fields that can come from multiple XBRL concepts (e.g., `net_income` can be `ProfitLoss`, `NetIncomeLoss`, or `NetIncome`), the mapping lists alternatives in priority order. `map_keys()` picks the first one present in the raw data.

**Industry-specific concepts:** Revenue mappings cover generic as well as industry-specific names (subscription revenue, royalty revenue, net interest income for banks, policy benefits for insurers, etc.), making the pipeline work across diverse sectors.

**Key functions:**

```python
map_keys(row: dict, mappings: dict) -> dict
# Translates one period's raw XBRL dict to internal field names.

map_all_periods(by_period: dict, mappings: dict) -> dict
# Applies map_keys to every period in a {period_end: raw_dict} structure.
```

---

### Schema & Validation

**`processing/schema.py`**

All data models are Pydantic v2 BaseModel subclasses. Every field is `Optional[float]` so missing data never crashes the pipeline; validators issue warnings instead of raising errors.

#### `CompanyMetadata`
| Field | Description |
|---|---|
| `cik` | SEC Central Index Key |
| `name` | Company name |
| `industry` | Industry classification |
| `fiscal_year_end` | Month/day of fiscal year end |
| `state_of_incorporation` | U.S. state |

#### `IncomeStatement`
Key fields: `revenue`, `cogs`, `gross_profit`, `ebit`, `interest_expense`, `tax_expense`, `net_income`, `depreciation`.

**Computed field:** `ebiat = ebit - tax_expense` (EBIT after taxes, used in DCF).

**Validators:**
- Gross profit reconciliation: warns if `|gross_profit - (revenue - cogs)|` > 1% of revenue.
- Tax rate sanity: warns if implied tax rate is outside 0–60%.

#### `BalanceSheet`
Key fields: `total_assets`, `total_liabilities`, `total_equity`, `current_assets`, `current_liabilities`, `cash`, `inventory`, `receivables`, `ppe_net`, `goodwill`, `long_term_debt`.

**Computed field:** `net_working_capital = current_assets - current_liabilities`.

**Validator:** Balance sheet identity — warns if `|assets - (liabilities + equity)|` > 1% of assets.

#### `CashFlowStatement`
Key fields: `cfo` (cash from operations), `capex`, `depreciation_amortization`, `net_income`.

**Computed field:** `fcf = cfo - capex` (free cash flow).

#### `PerShare`
Key fields: `basic_shares`, `diluted_shares`, `eps_basic`, `eps_diluted`, `book_value_per_share`, `dividends_per_share`.

#### `FinancialPeriod`
Aggregates the four statement models for one fiscal year:

```python
class FinancialPeriod(BaseModel):
    period_end: date
    income_statement: IncomeStatement
    balance_sheet: BalanceSheet
    cash_flow_statement: CashFlowStatement
    per_share: PerShare
```

**Validator:** Net income reconciliation — warns if IS net income and CFS net income differ by more than 1%.

#### `MarketData`
```python
class MarketData(BaseModel):
    ticker: str
    current_price: Optional[float]
    beta: Optional[float]
    shares_outstanding: Optional[float]
    market_cap: Optional[float]
    risk_free_rate: Optional[float]
```

#### `HistoricalFinancials`
Top-level container returned by the ETL pipeline:

```python
class HistoricalFinancials(BaseModel):
    ticker: str
    metadata: CompanyMetadata
    periods: list[FinancialPeriod]   # ordered oldest → newest
```

**Method:** `to_dataframe()` flattens all periods into a wide pandas DataFrame indexed by `period_end`. Useful for time-series analysis.

---

### Services (Orchestration)

**`services/financials.py`**

The single public API for the pipeline. Two functions:

```python
def get_financials(ticker: str, span: int = 5) -> HistoricalFinancials:
    ...

def get_market_data(ticker: str, include_rfr: bool = True) -> MarketData:
    ...
```

**`get_financials` internal steps:**

```
1. Edgar(ticker).fetch_all(span)
        ↓  {statement_type: {period: {xbrl_concept: value}}}

2. map_all_periods(raw_is, IS_MAPPINGS)
   map_all_periods(raw_bs, BS_MAPPINGS)
   map_all_periods(raw_cfs, CFS_MAPPINGS)
   map_all_periods(raw_ps, PS_MAPPINGS)
        ↓  {period: {internal_field: value}} for each statement

3. Union all periods across all four statements
        ↓  {period: {is_fields, bs_fields, cfs_fields, ps_fields}}

4. For each period → instantiate Pydantic models
   (validation + computed fields fire here)
        ↓  List[FinancialPeriod]

5. Wrap in HistoricalFinancials with metadata
        ↓  HistoricalFinancials
```

**`get_market_data` internal steps:**

```
1. fetch_yahoo_market(ticker)  → price, beta, shares, market_cap

2. fetch_risk_free_rate()      → 10Y Treasury (cached)

3. Return MarketData(...)
```

---

### Financial Ratios

**`services/ratio.py`**

Stateless calculation functions. All handle `None` and zero denominators gracefully.

#### Liquidity Ratios

| Function | Formula | Meaning |
|---|---|---|
| `current_ratio(CA, CL)` | CA / CL | Can short-term assets cover short-term liabilities? |
| `quick_ratio(CA, Inv, CL)` | (CA − Inv) / CL | Same but excluding less-liquid inventory |
| `cash_ratio(Cash, CL)` | Cash / CL | Most conservative liquidity measure |

#### Solvency Ratios

| Function | Formula | Meaning |
|---|---|---|
| `debt_to_equity(TL, TE)` | TL / TE | How leveraged is the company? |
| `debt_to_assets(TL, TA)` | TL / TA | What fraction of assets are debt-financed? |
| `interest_coverage(EBIT, IE)` | EBIT / IE | Can operating income service interest payments? |

#### Aggregator helpers

```python
get_liquidity_ratios(fin: HistoricalFinancials) -> dict[date, dict]
get_solvency_ratios(fin: HistoricalFinancials) -> dict[date, dict]
```

Both return `{period_end: {ratio_name: value}}` for all available periods.

---

### Agent (LLM Interface)

The agent is a **LangGraph ReAct loop** — it reasons step-by-step and calls tools when needed.

#### `agent/state.py` — State definition

```python
class AgentMemory(TypedDict):
    messages: Annotated[list, operator.add]  # accumulates turn by turn
    llm_calls: int
    max_llm_calls: int
    context: str
    response_type: str
```

`operator.add` on `messages` means new messages are appended, not overwritten.

#### `agent/tools.py` — Available tools

| Tool | What it does |
|---|---|
| `get_company_cik(ticker)` | Resolves a ticker symbol to its SEC CIK number via EDGAR |
| `get_risk_free_rate()` | Fetches the current 10Y Treasury yield from FRED |
| `get_market_data(ticker)` | Returns price, beta, shares outstanding, market cap from Yahoo Finance |

#### `agent/graph.py` — State machine

```
START
  │
  ▼
llm_call  ←─────────────────────────┐
  │                                  │
  │  should_continue()?              │
  ├─ tool_calls present              │
  │  AND llm_calls < max_llm_calls ──┤
  │                                  │
  ├─ otherwise ──→ END               │
  │                                  │
  ▼                                  │
tool_node                            │
(executes tool calls, appends        │
 ToolMessage results to state)  ─────┘
```

**Call budget:** `max_llm_calls` prevents runaway loops. The agent stops and returns its last message when the budget is exhausted.

#### `agent/prompts.py`

- **`agent_behavior`**: ReAct-style system prompt instructing the agent to reason step-by-step before calling tools.
- **`app_context`**: `"for a financial valuation system"` — appended to the system prompt.
- **`response_type`**: `"State your final answer in an investor thesis to investors format"` — shapes final output style.

#### `agent/memory.py` (WIP)

Proposes a nested dictionary structure for persistent agent memory:

```
dict[Entity, dict[Metric, dict[date, value]]]
```

Where `Entity` is a company ticker, `Metric` is a financial field name, and the innermost dict maps fiscal dates to values. Not yet integrated with the agent graph.

---

### API & CLI Harnesses

#### `main.py` + `api/routes.py`

FastAPI app currently exposes only stub endpoints:

| Endpoint | Response |
|---|---|
| `GET /` | `{"message": "Baboon Technologies API"}` |
| `GET /health` | `{"status": "ok"}` |

Financial data endpoints are not yet implemented.

**Run the server:**
```bash
uv run uvicorn backend.main:app --reload
```

#### `scripts/etl.py` — Human-readable CLI

Runs the full pipeline and prints formatted sections to stdout.

```bash
uv run python -m backend.scripts.etl AAPL
```

Sample output sections:
- Company metadata (name, CIK, fiscal year end, number of periods fetched)
- Latest period snapshot (revenue, EBIT, net income, assets, liabilities, equity, FCF, shares)
- Historical table (revenue / EBIT / net income by year)
- Market data (price, beta, shares outstanding, market cap, risk-free rate)

#### `scripts/etl_lean.py` — JSON CLI

Same pipeline, outputs `HistoricalFinancials` as pretty-printed JSON. Intended for piping or programmatic consumption.

```bash
uv run python -m backend.scripts.etl_lean AAPL
```

---

## Key Data Structures

### Complete `HistoricalFinancials` shape (simplified)

```
HistoricalFinancials
├── ticker: str
├── metadata: CompanyMetadata
│   ├── cik, name, industry
│   └── fiscal_year_end, state_of_incorporation
└── periods: [FinancialPeriod, ...]   # sorted oldest → newest
    ├── period_end: date
    ├── income_statement
    │   ├── revenue, cogs, gross_profit
    │   ├── ebit, ebiat  (computed)
    │   ├── interest_expense, tax_expense
    │   ├── net_income, depreciation
    │   └── ...
    ├── balance_sheet
    │   ├── total_assets, total_liabilities, total_equity
    │   ├── current_assets, current_liabilities
    │   ├── net_working_capital  (computed)
    │   ├── cash, inventory, receivables
    │   ├── ppe_net, goodwill, long_term_debt
    │   └── ...
    ├── cash_flow_statement
    │   ├── cfo, capex
    │   ├── fcf  (computed = cfo - capex)
    │   ├── depreciation_amortization
    │   └── ...
    └── per_share
        ├── basic_shares, diluted_shares
        ├── eps_basic, eps_diluted
        └── book_value_per_share, dividends_per_share
```

---

## Validation Logic

The pipeline is designed to **never crash on missing data** but to **warn loudly on inconsistencies**.

| Check | Where | Threshold |
|---|---|---|
| Gross profit: `GP ≈ Revenue − COGS` | `IncomeStatement` validator | > 1% of revenue |
| Tax rate sanity: `0% ≤ tax/ebit ≤ 60%` | `IncomeStatement` validator | outside range |
| Balance sheet identity: `Assets ≈ Liabilities + Equity` | `BalanceSheet` validator | > 1% of assets |
| NI reconciliation: IS net income ≈ CFS net income | `FinancialPeriod` validator | > 1% difference |
| Ratio denominators | `services/ratio.py` | Returns `None` if zero or None |

Validators emit `warnings.warn()` rather than raising exceptions so that a single bad period does not abort the entire pipeline.

---

## Configuration & Environment

All configuration is managed through Pydantic Settings (`core/config.py`) which reads from `.env`:

| Variable | Required | Description |
|---|---|---|
| `EDGAR_USER_AGENT` | Yes | Your email — required by SEC EDGAR ToS |
| `FRED_API_KEY` | Yes | FRED API key for Treasury rate data |
| `OPENAI_API_KEY` | Yes | OpenAI key for the LLM agent |
| `LLM_PROVIDER` | No | Default: `"openai"` |
| `LLM_MODEL` | No | Default: `"gpt-4o-mini"` |
| `APP_NAME` | No | Default: `"Baboon Technologies API"` |
| `ENVIRONMENT` | No | Default: `"development"` |

Copy `.env.example` to `.env` and fill in real values before running.

---

## Testing

Tests live under `backend/tests/unit/processing/`.

### `test_pipeline.py` — Integration tests

Runs the full ETL pipeline against 9 real tickers (AAPL, WMT, XOM, JNJ, BA, TSLA, T, KO, DIS). For each ticker, 14 assertions are checked:

- Pipeline completes without exception
- All three statements have exactly 3 periods
- Revenue is positive
- Net income, EBIT are present
- Gross profit consistency (≤ 1% deviation)
- Balance sheet identity (≤ 5% gap — wider tolerance for real-world data)
- Total assets positive, CapEx present, CFO present
- Net income reconciliation IS vs. CFS (≤ 1%)
- Periods aligned across statements

> Note: JPM (a bank) is explicitly excluded as an unsupported sector.

### `test_ratios.py` — Unit tests

Pure unit tests with synthetic data for every ratio function. Covers normal cases, zero denominators, None inputs, negative equity (insolvency), and multi-period dict inputs.

### `test_xbrl_map.py` — Mapping coverage tests

Validates that the four mapping dicts cover all required XBRL concepts for a complete DCF model — checking minimum entry counts and presence of specific fields (revenue, COGS, EBIT, CapEx, etc.).

**Run all tests:**
```bash
uv run pytest backend/tests/
```

---

## Work in Progress

### DCF Valuation Engine (`scripts/dcf_draft.py`, `scripts/dcf_variables.py`)

Skeleton files exist. The intended flow is:

```
HistoricalFinancials
    ↓ revenue growth + EBIT margin assumptions
Revenue / EBIT forecast (N years)
    ↓ WACC = weighted cost of equity (CAPM) + cost of debt
Discount each year's FCFF
    ↓ terminal value (Gordon growth or exit multiple)
Intrinsic value per share
```

Helper stubs (`interpolate`, `pct_change`) are present in `dcf_draft.py` but not yet connected to the data pipeline.

### Agent Memory (`agent/memory.py`)

The proposed `dict[Entity, dict[Metric, dict[date, value]]]` structure will allow the agent to retain financial data across conversation turns without re-fetching from EDGAR. Integration with `agent/graph.py` is pending.

### REST API (`api/routes.py`)

Planned endpoints to expose the pipeline over HTTP:

- `GET /financials/{ticker}` → `HistoricalFinancials` JSON
- `GET /market-data/{ticker}` → `MarketData` JSON
- `GET /ratios/{ticker}` → liquidity & solvency ratio dicts
- `POST /valuation/{ticker}` → DCF result (future)
