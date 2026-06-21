# Baboon Technologies — Final Documentation Report

**Project:** Baboon Technologies Financial Analysis Platform  
**Date:** June 19, 2026  
**Repository:** BaboonTechnologiesProject  

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Repository Structure](#repository-structure)
3. [Tech Stack & Dependencies](#tech-stack--dependencies)
4. [Architecture Overview](#architecture-overview)
5. [Backend Modules](#backend-modules)
   - [Adapters](#adapters-external-data-sources)
   - [Processing](#processing-data-transformation--validation)
   - [Services](#services-business-logic)
   - [Agent System](#agent-system-langgraph-state-machine)
   - [REST API](#rest-api)
   - [Authentication & Persistence](#authentication--persistence)
6. [Frontend](#frontend-reactvite-spa)
7. [Data Models](#data-models)
8. [Validation & Error Handling](#validation--error-handling)
9. [Caching Strategy](#caching-strategy)
10. [Testing](#testing)
11. [Configuration & Environment Variables](#configuration--environment-variables)
12. [Deployment](#deployment)
13. [Design Patterns & Best Practices](#design-patterns--best-practices)
14. [Known Limitations](#known-limitations)
15. [Key Files Reference](#key-files-reference)

---

## Executive Summary

**Baboon Technologies** is a full-stack financial analysis and company valuation platform designed to help investors research public companies. Users interact with a conversational AI agent that retrieves real financial data, computes valuations, and delivers structured investment analyses.

The system is composed of three main layers:

- **Frontend** — React 19 + Vite single-page application with Supabase authentication, chat session persistence, real-time streaming, and markdown rendering.
- **Backend** — FastAPI service hosting a 7-node LangGraph agent, a financial data ETL pipeline, valuation engines (DCF, comps, ratios), and multi-LLM provider support.
- **Data Sources** — SEC EDGAR XBRL filings, Yahoo Finance market data, FRED treasury rates, and NYU Stern Damodaran sector multiples.

The platform is production-ready with deployment configurations for Render (backend) and Vercel (frontend), supports multiple LLM providers (OpenAI, Anthropic, Groq, and others), and uses a multi-layer caching strategy to minimize redundant external API calls.

---

## Repository Structure

```
BaboonTechnologiesProject/
├── backend/                              # Python FastAPI service
│   ├── .env                             # Secrets (not committed)
│   ├── pyproject.toml                   # uv dependencies & build config
│   ├── uv.lock                          # Locked dependency graph
│   ├── render.yaml                      # Render.com deployment blueprint
│   └── src/backend/                     # Main Python package
│       ├── main.py                      # FastAPI app entry point
│       ├── core/
│       │   ├── config.py                # Pydantic Settings (reads .env)
│       │   └── llm.py                   # Per-node LLM initialization & caching
│       ├── api/
│       │   ├── routes.py                # REST endpoint definitions (12+ routes)
│       │   ├── schemas.py               # Request/response Pydantic schemas
│       │   └── controllers/
│       │       ├── agent.py             # Agent invocation & streaming handlers
│       │       ├── chats.py             # Chat session/message controllers
│       │       └── companies.py         # Financial data controllers
│       ├── auth/
│       │   └── dependencies.py          # Supabase bearer token verification
│       ├── db/
│       │   └── supabase.py              # Supabase REST client
│       ├── repositories/
│       │   └── chats.py                 # Chat session & message persistence
│       ├── adapters/                    # External data source wrappers
│       │   ├── edgar.py                 # SEC EDGAR XBRL via edgartools
│       │   ├── yahoo_finance.py         # Price, beta, shares, market cap
│       │   ├── fred.py                  # 10-year U.S. Treasury yield (DGS10)
│       │   └── damodaran.py             # Equity risk premium & sector multiples
│       ├── processing/                  # Data transformation & schema validation
│       │   ├── schema.py                # 20+ Pydantic financial models
│       │   └── xbrl_map.py              # ~285 XBRL concept mappings
│       ├── services/                    # Business logic layer
│       │   ├── financials.py            # EDGAR ETL orchestrator + LRU cache
│       │   ├── ratio.py                 # Financial ratio calculations
│       │   ├── growth.py                # Year-over-year growth rates
│       │   ├── dcf_engine.py            # DCF assumptions & valuation engine
│       │   ├── comparables.py           # Peer and Damodaran comparable analysis
│       │   ├── scrape.py                # DuckDuckGo search + async web scraping
│       │   └── agent_service.py         # Agent invocation (sync/async/streaming)
│       ├── agent/                       # LangGraph state machine
│       │   ├── main.py                  # CLI chatbot entry point
│       │   ├── graph.py                 # Graph definition & node wiring
│       │   ├── state.py                 # AgentState TypedDict
│       │   ├── llm.py                   # Structured output with prompt caching
│       │   ├── prompts.py               # System prompts for each node
│       │   ├── runtime.py               # activate_agent_async entry points
│       │   ├── constants.py             # RECURSION_LIMIT, REACT_LIMIT, JUDGE_LIMIT
│       │   ├── messages.py              # Message history helper utilities
│       │   ├── nodes/
│       │   │   ├── router.py            # Routing decision: tools vs. direct answer
│       │   │   ├── plan.py              # Tool execution planning
│       │   │   ├── tools.py             # Concurrent tool execution
│       │   │   ├── scrape.py            # Async web research node
│       │   │   ├── react.py             # Tool result evaluation
│       │   │   ├── response.py          # Final analysis composition
│       │   │   └── judge.py             # Quality evaluation & revision loop
│       │   ├── edges/                   # Conditional routing functions
│       │   │   ├── after_router.py
│       │   │   ├── after_plan.py
│       │   │   ├── after_react.py
│       │   │   └── after_judge.py
│       │   ├── tools/                   # Tool definitions & registry
│       │   │   ├── research.py          # get_financials, get_market_data, etc.
│       │   │   ├── calculation.py       # Ratios, growth, DCF, comparables
│       │   │   ├── base.py              # Shared helpers
│       │   │   └── registry.py          # Tool registration
│       │   ├── cache/                   # Session-scoped DuckDB cache
│       │   │   ├── base.py
│       │   │   ├── catalog.py
│       │   │   ├── merge.py
│       │   │   ├── schema.py
│       │   │   └── store.py
│       │   └── streaming/               # NDJSON event streaming
│       │       ├── events.py
│       │       └── stream.py
│       ├── scripts/                     # CLI development utilities
│       │   ├── etl.py                   # Full ETL pipeline (human-readable output)
│       │   ├── etl_lean.py              # Full ETL pipeline (JSON output)
│       │   ├── dcf.py                   # Standalone DCF calculation
│       │   └── agent_graph.py           # Export agent topology as PDF
│       └── tests/
│           └── unit/agent/
│               ├── test_cache_state_evolution.py
│               ├── test_graph_behavior.py
│               └── test_streaming.py
├── frontend/                            # React/Vite SPA
│   ├── package.json
│   ├── vite.config.js
│   ├── vercel.json
│   └── src/
│       ├── main.jsx
│       ├── App.jsx                      # Root component, routing & theme
│       ├── api/client.js                # API client with streaming support
│       ├── auth/
│       │   ├── AuthProvider.jsx         # Supabase Auth context provider
│       │   └── supabaseClient.js        # Supabase JS client initialization
│       ├── components/
│       │   ├── Navbar.jsx               # Theme toggle, health indicator
│       │   ├── ChatPage.jsx             # Main chat interface component
│       │   ├── SessionSidebar.jsx       # Session list & new chat button
│       │   ├── MessageBubble.jsx        # Message display with markdown
│       │   ├── ChatComposer.jsx         # Text input & submit button
│       │   ├── ReportMarkdown.jsx       # Markdown renderer
│       │   ├── ChatDataBackground.jsx
│       │   └── FinancialNetworkBackground.jsx
│       ├── pages/
│       │   ├── LandingPage.jsx
│       │   ├── ChatPage.jsx
│       │   ├── AuthPage.jsx
│       │   └── ProfilePage.jsx
│       ├── data/landingContent.js
│       ├── utils/reportExport.js
│       └── styles.css
├── Documentation/
│   ├── README.md
│   ├── ARCHITECTURE.md
│   ├── AGENTIC.md
│   ├── STATUS.md
│   ├── PROJECT_REPORT.md
│   ├── GitWorkflow.md
│   └── DEPLOYMENT.md
└── render.yaml                          # Root-level Render deployment config
```

---

## Tech Stack & Dependencies

### Backend (Python ≥ 3.11)

| Category | Libraries | Approximate Version |
|---|---|---|
| **Web framework** | FastAPI, uvicorn | 0.136.1, 0.46.0 |
| **Data validation** | Pydantic v2, pydantic-settings | 2.x, 2.14.0 |
| **Financial data** | edgartools, yfinance, pandas | ≥5.30.3, 1.3.0, 3.0.2 |
| **HTTP clients** | requests, httpx | 2.33.1, 0.28.0 |
| **HTML parsing** | BeautifulSoup4 | 4.12.0 |
| **LLM framework** | LangChain, LangGraph | 1.3.0, 1.2.0 |
| **LLM providers** | langchain-openai, langchain-anthropic, langchain-groq | 1.2.1, 0.3.0, 0.2.0 |
| **OpenAI SDK** | openai | 2.35.1 |
| **Web scraping** | Scrapy, duckduckgo-search | 2.12.0 |
| **Environment** | python-dotenv | 1.2.2 |
| **Testing** | pytest | 8.0.0+ |
| **Utilities** | xlrd, matplotlib, numpy, IPython | 2.0.2, 3.10.9, 2.4.4, 9.13.0 |

### Frontend (Node.js 18+)

| Library | Version |
|---|---|
| React | 19.2.3 |
| Vite | 7.2.7 |
| @supabase/supabase-js | 2.108.1 |
| react-markdown | 10.1.0 |
| remark-gfm | 4.0.1 |
| lucide-react | 0.561.0 |

---

## Architecture Overview

### System Layers

```
┌─────────────────────────────────────────────────────────────┐
│                    FRONTEND (React/Vite)                     │
│   AuthPage  →  ChatPage  →  MessageBubble (streaming)        │
└─────────────────────────┬───────────────────────────────────┘
                          │ HTTPS / NDJSON stream
┌─────────────────────────▼───────────────────────────────────┐
│                    FASTAPI BACKEND                           │
│   /agent/chat/stream  →  agent_service  →  LangGraph Agent  │
│   /companies/{ticker}/...  →  services/  →  adapters/        │
└──────────────┬─────────────────┬────────────────────────────┘
               │                 │
  ┌────────────▼──────┐  ┌───────▼──────────────────────────┐
  │  SUPABASE         │  │  EXTERNAL DATA SOURCES           │
  │  Auth, Sessions,  │  │  SEC EDGAR, Yahoo Finance,       │
  │  Messages         │  │  FRED, NYU Stern Damodaran       │
  └───────────────────┘  └──────────────────────────────────┘
```

### Request Data Flow (Agent Chat)

```
User message
    │
    ▼
POST /agent/chat/stream
    │
    ▼
agent_service.chat_stream_events_async()
    │
    ▼
LangGraph Agent (7-node state machine):
    │
    ├─ [1] ROUTER   → Decide: tools needed or answer directly?
    ├─ [2] PLAN     → Create ordered tool execution plan
    ├─ [3] TOOLS    → Execute tools concurrently (with session cache)
    ├─ [4] SCRAPE   → Optional async web research
    ├─ [5] REACT    → Evaluate results; request more tools or proceed
    ├─ [6] RESPONSE → Synthesize investor analysis
    └─ [7] JUDGE    → Quality check; revise or finalize
    │
    ▼
NDJSON event stream → React frontend → token-by-token rendering
```

---

## Backend Modules

### Adapters (External Data Sources)

The adapter layer wraps all external APIs behind clean Python interfaces. Each adapter is responsible for one data source and handles HTTP communication, error recovery, and initial normalization.

#### `edgar.py` — SEC EDGAR XBRL Wrapper

Extends `edgartools.Company` to fetch 10-K annual filings and normalize XBRL facts into a period-indexed dictionary.

- **Output format:** `{period_end_date: {xbrl_concept: numeric_value}}`
- **Deduplication logic:** When multiple XBRL facts exist for the same concept and period, the adapter prefers: `non-abstract → total-level → line item`. This prevents double-counting of subtotals vs. components.
- **Caching:** XBRL objects are cached per `(ticker, span)` to avoid repeat SEC requests within the same process.

#### `yahoo_finance.py` — Market Data

Fetches real-time and snapshot market data for a given ticker.

- **Returns:** `{current_price, beta, shares_outstanding, market_cap}`

#### `fred.py` — Risk-Free Rate

Fetches the 10-year U.S. Treasury yield (series `DGS10`) from the Federal Reserve Economic Data API.

- **Caching:** Module-level variable; cached for the process lifetime.

#### `damodaran.py` — Sector Multiples & Equity Risk Premium

Downloads the NYU Stern Damodaran Excel workbook to retrieve:

- Annual equity risk premiums by year.
- Sector-level valuation multiples: P/E, EV/EBITDA, price-to-book, etc.
- **Caching:** Module-level variable; cached for the process lifetime.

---

### Processing (Data Transformation & Validation)

#### `schema.py` — Pydantic Financial Models

Defines 20+ Pydantic v2 models that represent every layer of a company's financial data. All numeric fields are `Optional[float]` to tolerate missing XBRL data gracefully.

| Model | Key Fields | Computed Fields |
|---|---|---|
| `CompanyMetadata` | cik, name, sic, industry, fiscal_year_end | — |
| `IncomeStatement` | revenue, cogs, gross_profit, ebit, tax_expense, net_income, depreciation | ebiat, ebitda |
| `BalanceSheet` | total_assets, liabilities, equity, current assets/liabilities, cash, inventory, ppe, goodwill, long_term_debt | net_working_capital |
| `CashFlowStatement` | cfo, capex, depreciation, net_income | fcf |
| `PerShare` | basic_shares, diluted_shares, eps_basic, eps_diluted, book_value_per_share, dividends | — |
| `FinancialPeriod` | period_end, fiscal_year, income_statement, balance_sheet, cash_flow, per_share | — |
| `HistoricalFinancials` | ticker, metadata, periods[] | `to_dataframe()` |
| `MarketData` | current_price, beta, shares_outstanding, market_cap, risk_free_rate | — |
| `SectorData` | equity_risk_premium, long_term_growth_rate | — |
| `ValuationInputs` | risk_free_rate, beta, erp, cost_of_debt, market_cap, shares, total_debt, tax_rate, ltg | cost_of_capital, wacc |
| `Assumptions` | revenue_growth, ebit_margin, tax_rate, da_pct, capex_pct, nwc_pct | — |
| `DCFOutput` | intrinsic_value_per_share, terminal_value, pv_factors, projected_fcff, wacc, beta, sensitivity_table | — |

**Key Computed Fields:**

```
IncomeStatement.ebiat         = ebit − tax_expense
IncomeStatement.ebitda        = ebit + depreciation
BalanceSheet.net_working_capital = current_assets − current_liabilities
CashFlowStatement.fcf         = cfo − capex
ValuationInputs.cost_of_capital = rfr + beta × erp
ValuationInputs.wacc          = (CoE × w_equity) + (CoD × w_debt × (1 − tax_rate))
```

#### `xbrl_map.py` — XBRL Concept Mappings

Contains ~285 XBRL concept name mappings across four dictionaries (income statement, balance sheet, cash flow, per share). Each financial field maps to an ordered list of XBRL concept names tried in priority order, enabling multi-source fallback.

- Handles industry-specific concepts (banks, insurers, real estate trusts).
- Functions: `map_keys(row, mappings)` and `map_all_periods(by_period, mappings)`.

---

### Services (Business Logic)

#### `financials.py` — ETL Orchestrator

The central pipeline service. Coordinates all adapters and processing steps to produce validated `HistoricalFinancials` objects.

```
get_financials(ticker, span=5):
  1. edgar.get_xbrl_facts(ticker, span)       → raw XBRL dict
  2. xbrl_map.map_all_periods(raw, mappings)  → normalized dict
  3. schema.FinancialPeriod(**period)          → Pydantic validation
  4. schema.HistoricalFinancials(...)          → final object

get_cached_financials(ticker, span=5):
  → OrderedDict LRU(128) + per-key lock (thread-safe)
```

#### `ratio.py` — Financial Ratios

Computes ratios across all historical periods. Returns `List[float | None]` (one element per period); `None` is returned when the denominator is zero or missing.

| Category | Ratios |
|---|---|
| **Liquidity** | current_ratio, quick_ratio, cash_ratio |
| **Solvency** | debt_to_equity, debt_to_assets, interest_coverage |
| **Profitability** | gross_profit_margin, ebit_margin, net_margin, roe, roa |
| **Efficiency** | asset_turnover, receivables_turnover, inventory_turnover |

#### `growth.py` — Year-over-Year Growth Rates

Calculates annual growth as `(current − previous) / abs(previous)` for all income statement and balance sheet line items.

#### `dcf_engine.py` — Discounted Cash Flow Valuation

Three-stage pipeline:

1. **`build_assumptions(hf, md, sd)`** — Derives operating assumptions from historical averages: revenue growth rate, EBIT margin, effective tax rate, D&A as % of revenue, CapEx as % of revenue, and NWC as % of revenue.
2. **`build_valuation_inputs(hf, md, sd, assumptions)`** — Computes WACC via CAPM; estimates cost of equity and cost of debt from available data with three fallback calculation levels.
3. **`run_dcf(...)`** — Projects 5 years of unlevered free cash flow (FCFF), discounts to present value, computes terminal value using perpetuity growth (`TV = FCFF_final × (1 + ltg) / (wacc − ltg)`), and outputs intrinsic value per share plus a sensitivity table.

#### `comparables.py` — Comparable Company Analysis

Retrieves sector-level valuation multiples from the Damodaran dataset and applies them to the target company's financials. Supports P/E, EV/EBITDA, price-to-book, and other standard multiples.

#### `scrape.py` — Web Research

Combines DuckDuckGo search with asynchronous web page scraping to retrieve qualitative information (news, analyst commentary, company descriptions) that complements quantitative financial data.

#### `agent_service.py` — Agent Invocation

Provides three entry points into the LangGraph agent:

- `chat_sync(...)` — Blocking call for CLI use.
- `chat_async(...)` — Async call with awaitable result.
- `chat_stream_events_async(...)` — Async generator yielding NDJSON streaming events.

Uses `@lru_cache` to maintain a singleton agent instance across requests.

---

### Agent System (LangGraph State Machine)

The agent is a directed graph of 7 processing nodes connected by conditional edge functions. Each node receives the shared `AgentState`, performs its role, and updates the state before the graph routes to the next node.

#### Agent State

```python
class AgentState(TypedDict):
    messages: Annotated[list, operator.add]  # Full chat history (append-only)
    context: str                             # System-level guidance
    current_year: int
    available_tools: str                     # Serialized tool catalogue
    router_route: str                        # Last routing decision
    plan_status: str                         # e.g. "needs_tools", "needs_scrape_and_tools"
    react_iterations: int
    judge_iterations: int
    judge_verdict: str                       # "end" | "revise" | "gather_more"
    forced_response_due_to_recursion: bool
    data_catalog: dict                       # Summary of fetched datasets
    research_messages: list                  # Research tool results (cached)
    calculated_messages: list                # Calculation results (cached)
    scrape_history: list                     # Web research content
    tool_guidance: str                       # Tool selection reasoning
    deep_plan: bool                          # Whether deep analysis mode is active
    judge_rationale: str                     # Judge node critique
    current_response: str                    # Latest response_node output
    dialogue: list                           # User turns + final responses only
    query_count: int
```

#### The 7 Agent Nodes

**1. ROUTER** — Entry point for every user message.

The router uses an LLM with structured output (`RouterDecision`) to decide whether the question requires tool calls (financial data retrieval, calculations) or can be answered directly from existing context.

- **Routes to:** `plan_node` (tools needed) or `END` (direct answer).

**2. PLAN** — Tool orchestration planner.

Given the user question and the available tool catalogue, the plan node creates an ordered list of tool calls with per-tool reasoning (`PlanDecision`). It determines which data must be fetched first (e.g., `get_financials` before `get_ratios`) and whether web scraping is required.

- **Routes to:** the appropriate first tool group node.

**3. TOOLS** — Concurrent tool executor.

Executes all planned tools, looking up the session cache before making external API calls. When `HistoricalFinancials` is available in the cache, it is injected directly into dependent tools (ratios, growth, DCF) without re-fetching.

**4. SCRAPE** — Asynchronous web research node.

Performs DuckDuckGo searches and scrapes relevant web pages asynchronously. Uses a fast LLM (Groq) to synthesize scraped content into structured summaries before appending to `scrape_history`.

**5. REACT** — Tool result evaluation.

Reviews all gathered data against the original question. Either determines that enough information is available to compose an answer, or identifies gaps and requests additional tool calls. Respects `force_final_answer` when the LLM call budget is exhausted.

- **Routes to:** more tools, `response_node`, or `END`.

**6. RESPONSE** — Final analysis composition.

Uses a reasoning-heavy LLM (typically Anthropic Claude) to synthesize all research and calculation results into a structured investor analysis. Supports Anthropic prompt caching to reduce costs on repeated calls within a session.

- **Routes to:** `judge_node` or `END`.

**7. JUDGE** — Quality evaluation and revision loop.

Evaluates the quality of the response against the user's question. Outputs one of three verdicts:
- `"end"` — Response is satisfactory; conversation finishes.
- `"revise"` — Response needs editing; loops back to `response_node`.
- `"gather_more"` — More data is needed; loops back to `react_node`.

#### Budget Enforcement

```python
RECURSION_LIMIT = 10   # Maximum total node iterations per request
REACT_LIMIT     = 2    # Maximum react_node calls per request
JUDGE_LIMIT     = 1    # Maximum judge_node calls per response
```

When the LLM call budget is exhausted, `forced_response_due_to_recursion = True` is set and the response node produces a best-effort final answer from whatever data is available.

#### Tool Registry

**Research tools** (retrieve external data):

| Tool | Description |
|---|---|
| `get_financials` | Fetches and normalizes 5 years of SEC EDGAR statements |
| `get_market_data` | Retrieves current price, beta, shares outstanding, market cap |
| `get_sector_data` | Returns equity risk premium and long-term growth rate |
| `scrape_web` | DuckDuckGo search + async page scraping |

**Calculation tools** (transform retrieved data):

| Tool | Description |
|---|---|
| `get_financial_ratios` | Liquidity, solvency, profitability, efficiency ratios |
| `get_growth_rates` | Year-over-year revenue, margin, and asset growth |
| `get_dcf_valuation` | Full DCF valuation with sensitivity table |
| `get_comparable_analysis` | Peer multiples via Damodaran sector data |

#### Streaming Event Format

The `/agent/chat/stream` endpoint emits NDJSON events:

```json
{"type": "thread",  "thread_id": "abc123"}
{"type": "status",  "text": "Fetching financial statements for AAPL..."}
{"type": "thought", "content": "Calling: get_financials(ticker='AAPL', span=5)"}
{"type": "delta",   "content": "Apple reported revenue of $391B in FY2025..."}
{"type": "done"}
```

---

### REST API

All endpoints are defined in `backend/src/backend/api/routes.py`.

| Method | Endpoint | Auth Required | Description |
|---|---|---|---|
| `GET` | `/` | No | Service identity |
| `GET` | `/health` | No | Health check |
| `GET` | `/companies/{ticker}/financials` | No | 5 years of normalized financial statements |
| `GET` | `/companies/{ticker}/market-data` | No | Current price, beta, market cap, risk-free rate |
| `GET` | `/companies/{ticker}/ratios` | No | Liquidity, solvency, and profitability ratios |
| `GET` | `/companies/{ticker}/growth` | No | Year-over-year growth rates |
| `GET` | `/companies/{ticker}/dcf` | No | DCF intrinsic value estimate |
| `GET` | `/sector-data` | No | Equity risk premium and long-term growth rate |
| `POST` | `/agent/chat` | Optional | Synchronous agent response |
| `POST` | `/agent/chat/stream` | Optional | Streaming agent response (NDJSON) |
| `GET` | `/chat` | Yes | List chat sessions for authenticated user |
| `POST` | `/chat` | Yes | Create new chat session |
| `GET` | `/chat/{sessionId}/messages` | Yes | Get all messages in a session |
| `GET` | `/auth/me` | Yes | Retrieve authenticated user profile |
| `PUT` | `/auth/me` | Yes | Update authenticated user profile |

---

### Authentication & Persistence

**Supabase** handles both authentication and database persistence.

- `auth/dependencies.py` — FastAPI dependency that verifies Supabase JWT bearer tokens on protected routes.
- `db/supabase.py` — Thin REST client wrapping the Supabase HTTP API.
- `repositories/chats.py` — Data access layer for chat sessions and messages.

**Database Tables:**

| Table | Purpose |
|---|---|
| `users` | Supabase managed auth users |
| `profiles` | Extended user profile fields |
| `chat_sessions` | Session metadata (id, title, user_id, created_at) |
| `chat_messages` | Individual messages (session_id, role, content, timestamp) |

---

## Frontend (React/Vite SPA)

### Key Components

| Component | File | Responsibility |
|---|---|---|
| Root | `App.jsx` | App state, routing, theme management |
| Chat interface | `ChatPage.jsx` | Session management, message display, streaming |
| Message display | `MessageBubble.jsx` | Markdown rendering, streaming indicator |
| Input | `ChatComposer.jsx` | Text entry and submit |
| Sidebar | `SessionSidebar.jsx` | Session list and new chat creation |
| Navigation | `Navbar.jsx` | Theme toggle, API health indicator |
| Authentication | `AuthPage.jsx` | Supabase email/password login & signup |
| Profile | `ProfilePage.jsx` | User profile view and edit |
| Landing | `LandingPage.jsx` | Marketing landing page |

### State Management

The frontend uses React's built-in `useState` without an external store (no Redux or Zustand). Session state is persisted to `localStorage` for page refresh survival. Authentication state is managed via a Supabase Auth context (`AuthProvider.jsx`).

### Session Data Model

```javascript
{
  id: "uuid",
  title: "Analyze Apple's profitability trends",
  threadId: "backend-agent-thread-id",
  messages: [
    {
      id: "uuid",
      role: "user" | "assistant",
      content: "...",
      timestamp: "ISO 8601",
      isStreaming: false,
      statusText: "Fetching financial statements...",
      thoughts: ["Calling get_financials(AAPL)", "..."]
    }
  ],
  updatedAt: "ISO 8601"
}
```

### Streaming Integration

The API client (`api/client.js`) connects to `/agent/chat/stream` and parses incoming NDJSON events. The chat page updates the active message in place as `delta` events arrive, producing token-by-token rendering. `status` events update a visible status line below the message; `thought` events populate an expandable "thoughts" section.

---

## Data Models

### `HistoricalFinancials` — Central Data Object

This is the primary data structure produced by the ETL pipeline and consumed by all calculation services and agent tools.

```
HistoricalFinancials
├── ticker: str
├── metadata: CompanyMetadata
│   ├── cik, name, sic, industry
│   ├── fiscal_year_end, website, phone
└── periods: List[FinancialPeriod]
    ├── period_end: date
    ├── fiscal_year: str                  ("FY2025")
    │
    ├── income_statement: IncomeStatement
    │   ├── revenue
    │   ├── cost_of_goods_sold
    │   ├── gross_profit
    │   ├── ebit
    │   ├── ebiat                         (computed: ebit − tax_expense)
    │   ├── ebitda                        (computed: ebit + depreciation)
    │   ├── tax_expense
    │   ├── net_income
    │   └── depreciation_expense
    │
    ├── balance_sheet: BalanceSheet
    │   ├── total_assets
    │   ├── total_liabilities
    │   ├── total_equity
    │   ├── net_working_capital           (computed: current_assets − current_liabilities)
    │   ├── current_assets, current_liabilities
    │   ├── cash_and_equivalents
    │   ├── accounts_receivable, inventory
    │   ├── property_plant_equipment_net
    │   ├── goodwill
    │   └── long_term_debt
    │
    ├── cash_flow_statement: CashFlowStatement
    │   ├── cash_from_operations
    │   ├── capital_expenditures
    │   ├── free_cash_flow                (computed: cfo − capex)
    │   ├── depreciation_amortization
    │   └── net_income
    │
    └── per_share: PerShare
        ├── basic_shares, diluted_shares
        ├── eps_basic, eps_diluted
        ├── book_value_per_share
        └── dividends_per_share
```

---

## Validation & Error Handling

The system applies a "warn, don't crash" philosophy. Pydantic validators emit warnings for data quality issues but allow the pipeline to complete so downstream consumers can decide how to handle partial data.

| Validation Check | Location | Tolerance | Action |
|---|---|---|---|
| `gross_profit ≈ revenue − cogs` | `IncomeStatement` | > 1% of revenue | Warning logged |
| `0% ≤ effective_tax_rate ≤ 60%` | `IncomeStatement` | Outside range | Warning logged |
| `assets ≈ liabilities + equity` | `BalanceSheet` | > 1% of assets | Warning logged |
| `IS net_income ≈ CFS net_income` | `FinancialPeriod` | > 1% difference | Warning logged |
| `wacc > long_term_growth` | `ValuationInputs` | Always enforced | Warning logged |
| Division by zero in ratios | All ratio functions | Denominator is 0 or None | Returns `None` |

All Optional fields return `None` rather than raising exceptions, allowing partial data to flow through the full pipeline.

---

## Caching Strategy

The system uses a three-layer caching hierarchy to minimize redundant external API calls:

| Layer | Mechanism | Scope | Cached Data |
|---|---|---|---|
| **Adapter** | Module-level Python variable | Process lifetime | FRED treasury rate, Damodaran Excel data |
| **Service** | `OrderedDict` LRU(128) + per-key lock | Process lifetime, per ticker/span | `HistoricalFinancials` objects |
| **Agent session** | `AgentState` dict + DuckDB | Single conversation thread | Tool call results; deduplicates within a session |

The service-layer cache is thread-safe via per-key locks, preventing duplicate external calls when multiple concurrent requests arrive for the same ticker.

Anthropic prompt caching is also enabled on the response node: the large financial dataset injected into the system prompt is cached across multiple turns of the same conversation, reducing token costs.

---

## Testing

Tests are located in `backend/tests/unit/agent/` and cover three critical system behaviors:

| Test File | What It Tests |
|---|---|
| `test_cache_state_evolution.py` | Session cache correctness: data written and read back consistently across tool calls |
| `test_graph_behavior.py` | Agent routing logic: correct node transitions given different router and react decisions |
| `test_streaming.py` | NDJSON event ordering: events emitted in the correct sequence (thread → status → thought → delta → done) |

**Running tests:**

```bash
cd backend
uv run pytest tests/
```

---

## Configuration & Environment Variables

All configuration is loaded via Pydantic Settings from `backend/.env`.

### Required Variables

| Variable | Purpose |
|---|---|
| `EDGAR_USER_AGENT` | Your email address — required by SEC Terms of Service |
| `FRED_API_KEY` | Federal Reserve Economic Data API key |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase client-side (anon) key |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase server-side (service role) key |
| `CORS_ORIGINS` | Comma-separated list of allowed frontend origins |

### LLM Provider Variables

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `openai` | Default LLM provider for all nodes |
| `LLM_MODEL` | `gpt-4o-mini` | Default model for all nodes |
| `OPENAI_API_KEY` | — | Required if using OpenAI |
| `ANTHROPIC_API_KEY` | — | Required if using Anthropic |
| `GROQ_API_KEY` | — | Required if using Groq |

### Per-Node LLM Overrides

Each node can independently use a different provider and model:

```env
# High-reasoning nodes — use a strong model
RESPONSE_LLM_PROVIDER=anthropic
RESPONSE_LLM_MODEL=claude-sonnet-4-6

# Fast routing decisions — use a cheaper model
ROUTER_LLM_PROVIDER=openai
ROUTER_LLM_MODEL=gpt-4o-mini

# Scraping synthesis — use a fast, cheap model
SCRAPE_LLM_PROVIDER=groq
SCRAPE_LLM_MODEL=llama-3.3-70b-versatile

# Quality evaluation
JUDGE_LLM_PROVIDER=openai
JUDGE_LLM_MODEL=gpt-4o
```

### Frontend Environment Variable

| Variable | Purpose |
|---|---|
| `VITE_API_BASE_URL` | Backend base URL (e.g., `https://your-backend.onrender.com`) |

---

## Deployment

### Backend — Render.com

The `backend/render.yaml` (also mirrored at root `render.yaml`) defines the Render deployment blueprint:

```yaml
runtime: python
rootDir: backend
buildCommand: pip install uv && uv sync --frozen
startCommand: uv run uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

Required environment variables must be set in the Render dashboard: `EDGAR_USER_AGENT`, `FRED_API_KEY`, LLM provider keys, and all `SUPABASE_*` variables.

Set `CORS_ORIGINS` to the Vercel frontend URL once it is known.

### Frontend — Vercel

```
Root directory: frontend
Build command:  npm run build
Output dir:     dist
```

Set `VITE_API_BASE_URL` to the Render backend URL in the Vercel environment variables panel.

---

## Design Patterns & Best Practices

### 1. Layered Architecture

```
Adapters (external API calls)
    → Processing (XBRL mapping + Pydantic validation)
        → Services (business logic orchestration)
            → API controllers (HTTP interface)
                → Agent (LLM-driven decision making)
```

Each layer has a single, clear responsibility. Adapters never contain business logic; services never make raw HTTP calls.

### 2. Structured LLM Output

Every LLM invocation uses `.with_structured_output(Schema, method="function_calling")`, ensuring deterministic routing decisions via Pydantic schema enforcement. This eliminates parsing ambiguity and makes agent behavior testable.

### 3. Fallback Priority Chains

Multiple levels of fallback are built in throughout:

- **XBRL mappings** — Each field lists 3–5 XBRL concept names tried in order.
- **WACC cost of debt** — Three calculation methods tried in order: interest expense / total debt, cash flow statement interest, derived from spread.
- **Risk-free rate** — Falls back to a hardcoded constant if the FRED API is unavailable.

### 4. Budget-Constrained Agent

The agent enforces strict limits on LLM calls, react iterations, and judge iterations. When budgets are exhausted, `forced_response_due_to_recursion = True` triggers a best-effort final answer rather than hanging or erroring.

### 5. Dependency-Aware Tool Execution

Financial calculation tools (`get_ratios`, `get_growth_rates`, `get_dcf`) depend on `HistoricalFinancials`. The agent injects the cached result from an earlier `get_financials` call at runtime, rather than requiring tools to re-fetch independently. This prevents duplicate EDGAR requests within a session.

### 6. Session Isolation

All per-request state (agent cache, message history, data catalog, DuckDB) is scoped to a single conversation thread. There is no shared mutable state between concurrent user sessions.

### 7. Real-Time Streaming UX

The frontend receives NDJSON events incrementally, displaying progress status, internal "thoughts," and the response content as tokens arrive. This produces a responsive feel even for analyses that take 10–30 seconds to complete.

---

## Known Limitations

1. **EDGAR / edgartools stability** — The XBRL adapter depends on the `edgartools` library's internal structure. Changes to how SEC EDGAR reports XBRL facts, or breaking changes in `edgartools`, could require adapter updates. Some financial statement structures differ significantly across industries (e.g., banks, insurance companies, REITs).

2. **DCF simplicity** — The DCF model uses 5-year linear projections derived from historical averages. It does not apply industry-specific growth adjustments or support multi-stage growth models. Terminal growth rate defaults to 2.5%.

3. **Web scraping reliability** — Async scraping may time out or be blocked by sites that require JavaScript rendering or rate-limit crawlers. Content accuracy depends on the target site's HTML structure.

4. **Session cache is in-memory** — The DuckDB cache is per-process and non-persistent. Restarting the backend clears all cached financial data. The LRU service cache also resets on restart.

5. **Peer selection is manual** — Comparable analysis uses Damodaran sector-level multiples, which are annual snapshots rather than real-time data. The system does not automatically identify individual peer companies; sector assignment depends on the company's SIC code.

6. **No retry logic on adapter failures** — If the EDGAR, Yahoo Finance, or FRED fetch fails, the error propagates immediately without retry. Callers must handle exceptions.

---

## Key Files Reference

| File | Purpose |
|---|---|
| [backend/src/backend/main.py](backend/src/backend/main.py) | FastAPI app initialization, middleware, CORS |
| [backend/src/backend/core/config.py](backend/src/backend/core/config.py) | All environment variable definitions and defaults |
| [backend/src/backend/core/llm.py](backend/src/backend/core/llm.py) | LLM instance creation with per-node override logic |
| [backend/src/backend/agent/graph.py](backend/src/backend/agent/graph.py) | LangGraph node wiring and edge routing |
| [backend/src/backend/agent/state.py](backend/src/backend/agent/state.py) | `AgentState` TypedDict definition |
| [backend/src/backend/agent/prompts.py](backend/src/backend/agent/prompts.py) | System prompts for all 6 LLM-calling nodes |
| [backend/src/backend/agent/constants.py](backend/src/backend/agent/constants.py) | RECURSION_LIMIT, REACT_LIMIT, JUDGE_LIMIT |
| [backend/src/backend/processing/schema.py](backend/src/backend/processing/schema.py) | All 20+ Pydantic financial models |
| [backend/src/backend/processing/xbrl_map.py](backend/src/backend/processing/xbrl_map.py) | ~285 XBRL concept → field mappings |
| [backend/src/backend/services/financials.py](backend/src/backend/services/financials.py) | ETL orchestrator + thread-safe LRU cache |
| [backend/src/backend/services/dcf_engine.py](backend/src/backend/services/dcf_engine.py) | DCF assumption derivation and valuation |
| [backend/src/backend/services/ratio.py](backend/src/backend/services/ratio.py) | All financial ratio calculations |
| [backend/src/backend/api/routes.py](backend/src/backend/api/routes.py) | All REST endpoint definitions |
| [backend/src/backend/agent/streaming/events.py](backend/src/backend/agent/streaming/events.py) | NDJSON event type definitions |
| [frontend/src/App.jsx](frontend/src/App.jsx) | React app root, state orchestration, routing |
| [frontend/src/api/client.js](frontend/src/api/client.js) | API client with NDJSON streaming parser |
| [frontend/src/auth/AuthProvider.jsx](frontend/src/auth/AuthProvider.jsx) | Supabase Auth context provider |
| [render.yaml](render.yaml) | Render.com deployment blueprint |
| [frontend/vercel.json](frontend/vercel.json) | Vercel SPA routing config |
