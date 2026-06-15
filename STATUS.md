# Baboon Technologies — Architecture Reference

## Overview

Baboon Technologies is a financial analysis platform that combines SEC filing ingestion, quantitative valuation models, and an LLM-powered conversational agent. Users interact through a React chat interface; the backend fetches and processes company financials, then routes queries through a LangGraph agent that calls specialized tools and streams responses in real time.

---

## Repository Layout

```
BaboonTechnologiesProject/
├── backend/                  Python / FastAPI
│   ├── pyproject.toml        uv package manager (Python ≥ 3.11)
│   ├── .env / .env.example
│   └── src/backend/
│       ├── main.py           FastAPI entry point
│       ├── core/             Config & LLM initialisation
│       ├── api/              HTTP layer (routes, schemas, controllers)
│       ├── adapters/         External data sources
│       ├── processing/       XBRL mapping & Pydantic models
│       ├── services/         Business logic / ETL
│       ├── agent/            LangGraph state machine & tools
│       └── scripts/          CLI utilities & graph exporter
├── frontend/                 React / Vite SPA
│   ├── package.json
│   ├── vercel.json
│   └── src/
│       ├── App.jsx
│       ├── api/client.js
│       └── components/
├── render.yaml               Render.com deployment config
└── requirements.txt
```

---

## Backend Layers

### 1. Adapters (`adapters/`)

Thin wrappers around external data sources. Each returns normalised Python dicts or scalars.

| Module | Source | Output |
|---|---|---|
| `edgar.py` | SEC EDGAR (via `edgartools`) | `{period_end: {xbrl_concept: value}}` |
| `yahoo_finance.py` | Yahoo Finance (`yfinance`) | `{current_price, beta, shares_outstanding, market_cap}` |
| `fred.py` | Federal Reserve FRED API | `float` (10-year Treasury rate) |
| `damodaran.py` | NYU Stern Excel file | `float` (annual equity risk premium) |

`fred` and `damodaran` results are module-level cached to avoid repeat network calls within a process lifetime.

---

### 2. Processing (`processing/`)

**`xbrl_map.py`** — Maps ~285 SEC XBRL concepts to short internal field names across four dictionaries:

- `IS_MAPPINGS` (~98 concepts) → Income Statement fields
- `BS_MAPPINGS` (~107 concepts) → Balance Sheet fields
- `CFS_MAPPINGS` (~70 concepts) → Cash Flow Statement fields
- `PS_MAPPINGS` (~12 concepts) → Per-Share fields

Each field lists concept names in priority order; the adapter applies the first concept found in the filing.

**`schema.py`** — 20+ Pydantic v2 models. Key types:

| Model | Description |
|---|---|
| `CompanyMetadata` | CIK, SIC, incorporation state, FYE |
| `IncomeStatement` | Revenue → Net Income; computed `ebiat` |
| `BalanceSheet` | Assets, liabilities, equity; computed `net_working_capital`; balance-sheet identity validator |
| `CashFlowStatement` | CFO, CapEx, D&A; computed `fcf` |
| `PerShare` | Shares, EPS, dividends |
| `FinancialPeriod` | All four statements for one fiscal year |
| `HistoricalFinancials` | Ordered list of `FinancialPeriod` + metadata; exposes `to_dataframe()` |
| `MarketData` | Price, beta, market cap, risk-free rate |
| `SectorData` | Equity risk premium, long-term growth rate |
| `Assumptions` | DCF model assumptions derived from history |
| `DCFOutput` | Intrinsic value, per-share value, sensitivity table |

Design conventions: all financial fields are `float | None`; validators warn rather than raise; computed fields use `@computed_field`.

---

### 3. Services (`services/`)

**`financials.py`** — ETL orchestrator:
1. Calls `Edgar(ticker).fetch_all(span)` for raw XBRL facts
2. Applies `xbrl_map` to normalise fields
3. Instantiates Pydantic models (validation + computed fields)
4. Returns `HistoricalFinancials`

Public API:
```python
get_financials(ticker, span=5) -> HistoricalFinancials
get_cached_financials(ticker, span=5) -> HistoricalFinancials   # LRU(128) + per-key lock
get_market_data(ticker, include_rfr=True) -> MarketData
get_sector_data(year=None) -> SectorData
```

**`ratio.py`** — Stateless financial ratio functions (liquidity, solvency, profitability, efficiency). All handle `None` and zero-denominator gracefully. Aggregator functions return `{date: {metric: value}}`.

**`growth.py`** — Year-over-year growth rates: `(curr − prev) / abs(prev)`. Covers Income Statement and Balance Sheet fields.

**`dcf_engine.py`** — Three-step DCF pipeline:
1. `build_assumptions()` — derives operating assumptions from history
2. `build_valuation_inputs()` — computes WACC via CAPM
3. `run_dcf()` — projects free cash flows, discounts, adds terminal value

**`agent_service.py`** — Initialises the LangGraph agent once (via `@lru_cache`) and exposes synchronous, async, and streaming entry points used by the API controllers.

---

### 4. API (`api/`)

**`routes.py`** — All REST endpoints:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/companies/{ticker}/financials` | Historical statements (default 5 years) |
| `GET` | `/companies/{ticker}/market-data` | Current price, beta, market cap, RFR |
| `GET` | `/companies/{ticker}/ratios` | Liquidity, solvency, profitability ratios |
| `GET` | `/companies/{ticker}/growth` | YoY growth rates |
| `GET` | `/companies/{ticker}/dcf` | DCF valuation |
| `GET` | `/sector-data` | Equity risk premium & long-term growth |
| `POST` | `/agent/chat` | Synchronous agent chat |
| `POST` | `/agent/chat/stream` | Streaming agent chat (NDJSON) |

**Streaming event format** (`/agent/chat/stream`):
```json
{"type": "thread",  "thread_id": "..."}
{"type": "status",  "text": "Fetching financial statements..."}
{"type": "thought", "content": "Requesting: get_financials(AAPL)"}
{"type": "delta",   "content": "Here is the analysis..."}
{"type": "done"}
```

**`schemas.py`** — Pydantic request/response models: `AgentChatRequest`, `AgentChatResponse`, `RatiosResponse`, `GrowthResponse`, `DCFResponse`.

**`controllers/`** — Thin delegation layer between routes and services; `companies.py` for financial endpoints, `agent.py` for chat endpoints.

---

### 5. Agent (`agent/`)

The agent is a LangGraph state machine that plans tool calls, executes them, caches results, and synthesises a final response.

#### State (`state.py`)

```python
class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]  # append-only
    context: str                    # system prompt context
    current_year: int
    available_tools: dict           # serialised tool catalogue
    router_route: str               # last routing decision
    plan_status: str                # tool plan status
    forced_response_due_to_recursion: bool
    data_cache: dict                # fetched data keyed by ticker/tool
    data_catalog: dict              # cache metadata
```

#### Graph (`graph.py`)

```
START → router
          ├─ "end" ──────────────────────────────────────→ END
          └─ "plan_node" → plan_node
                             ├─ "market_data_node" → tools_node ─┐
                             ├─ "sector_data_node" → tools_node  ├─→ plan_node
                             ├─ "financials_node"  → tools_node ─┘
                             └─ "response_node" → response_node → END
```

| Node | Role |
|---|---|
| `router` | LLM with structured output decides: answer directly or call tools |
| `plan_node` | LLM generates ordered tool plan; routes to the first pending tool group |
| `tools_node` | Executes tools, checks cache first, stores results, loops to `plan_node` |
| `response_node` | LLM synthesises gathered data into investor-thesis answer; can request more tools if budget permits |

Budget enforcement: `max_llm_calls` recursion limit prevents runaway loops; `forced_response_due_to_recursion` flag triggers a mandatory final answer.

#### Tools (`tools.py`)

**Research tools** (hit external APIs):
- `get_financials(ticker)` → `HistoricalFinancials`
- `get_market_data(ticker)` → `MarketData`
- `get_sector_data(year)` → `SectorData`

**Calculation tools** (consume cached `HistoricalFinancials`; only `ticker` needed in the plan):
- `get_liquidity_ratios`, `get_solvency_ratios`, `get_profitability_ratios`, `get_efficiency_ratios`
- `get_income_statement_growth_rates`, `get_balance_sheet_growth_rates`
- `get_dcf`

#### Cache (`cache.py`, `cache_schema.py`)

Session-scoped, stored in `AgentState.data_cache`:

```
{
  "companies": {
    "AAPL": {
      "searched":   { "get_financials": {...}, "get_market_data": {...} },
      "calculated": { "get_liquidity_ratios": {...}, "get_dcf": {...} }
    }
  },
  "global": {
    "sector_data_by_year": { 2025: {...} }
  }
}
```

Avoids duplicate API calls within a session. Research tools populate `searched`; calculation tools populate `calculated` and auto-inject the cached `HistoricalFinancials` so the LLM never needs to pass raw data.

#### Helpers (`graph_helpers.py`)

Routing, tool scheduling, cache lookup, and serialisation utilities used by graph nodes. Key functions: `run_planned_tools()`, `run_financial_dependent_tools()`, `next_route_from_tool_plan()`, `serialize_tools()`.

#### Prompts (`prompts.py`)

Four system prompts with distinct roles:
- `app_context` — agent identity (financial analyst, evidence-based)
- `router_prompt` — scope gate (direct answer vs. tool plan)
- `plan_prompt` — tool selection and ordering logic
- `response_prompt` — synthesis and optional further tool requests

---

### 6. Core (`core/`)

**`config.py`** — Pydantic `Settings` loaded from `.env`:

| Variable | Purpose |
|---|---|
| `EDGAR_USER_AGENT` | Required by SEC EDGAR |
| `FRED_API_KEY` | Federal Reserve API |
| `OPENAI_API_KEY` | LLM provider |
| `LLM_PROVIDER` / `LLM_MODEL` | e.g. `openai` / `gpt-4o-mini` |
| `CORS_ORIGINS` | Comma-separated allowed origins |
| `LANGSMITH_*` | Optional LangSmith tracing |

**`llm.py`** — Initialises the LangChain chat model from config. Temperature fixed at 0 for deterministic outputs.

---

## Frontend

### Tech Stack

- React 19, Vite 7, `react-markdown` + `remark-gfm`, `lucide-react`
- No global state library; state lives in `App.jsx` and is persisted to `localStorage`

### Component Tree

```
App
├── Navbar                (theme toggle, API health indicator)
├── LandingPage           (home / intro)
└── ChatPage
    ├── SessionSidebar    (session list, new chat)
    ├── MessageBubble[]   (user & assistant messages)
    ├── ChatComposer      (text input + submit)
    └── ChatDataBackground
```

### Session Model (`localStorage`)

```js
{
  activeSessionId: "uuid",
  sessions: [{
    id: "uuid",
    title: "...",
    threadId: "backend-thread-id",
    messages: [{
      id, role, content, timestamp,
      isStreaming, statusText, thoughts: []
    }],
    updatedAt: "ISO"
  }]
}
```

### API Client (`api/client.js`)

Wraps `fetch` with typed event callbacks for the NDJSON stream:
```js
streamChatMessage({ message, threadId, onThreadId, onStatus, onThought, onDelta, onDone, onError })
```

---

## Data Flow (End-to-End)

```
User message → POST /agent/chat/stream
    → agent_service.chat_stream_events_async()
    → LangGraph: router → plan_node → tools_node → response_node
        tools_node calls:
            get_financials("AAPL")  →  edgar adapter  →  EDGAR API
            get_profitability_ratios(hf=<cached>)  →  ratio service
    → NDJSON stream: status / thought / delta events
    → Frontend renders token-by-token in MessageBubble
```

---

## Caching Strategy

| Layer | Mechanism | Scope |
|---|---|---|
| Adapter (FRED, Damodaran) | Module-level variable | Process lifetime |
| Service (`get_cached_financials`) | `functools.lru_cache(128)` + threading lock | Process lifetime, per `(ticker, span)` |
| Agent (`data_cache` in state) | Dict in `AgentState` | Single conversation thread |

---

## Testing

```
backend/tests/unit/agent/test_streaming.py
```

Covers stream event ordering, status deduplication, direct-router path (no status emitted), and fallback delta behaviour. Run with:

```bash
cd backend && uv run pytest tests/
```

---

## Deployment

### Backend — Render

```yaml
runtime: python
rootDir: backend
buildCommand: pip install uv && uv sync --frozen
startCommand: uv run uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

Required env vars: `EDGAR_USER_AGENT`, `FRED_API_KEY`, `OPENAI_API_KEY`, `LLM_PROVIDER`, `LLM_MODEL`, `CORS_ORIGINS`.

### Frontend — Vercel

Root: `frontend` | Build: `npm run build` | Output: `dist`

Env: `VITE_API_BASE_URL=https://<render-service>.onrender.com`

---

## Key Dependencies

| Package | Version | Role |
|---|---|---|
| FastAPI | 0.136.1 | Web framework |
| LangChain | 1.3.0 | LLM toolkit |
| LangGraph | 1.2.0 | Agent state machine |
| edgartools | ≥ 5.30.3 | SEC EDGAR client |
| yfinance | 1.3.0 | Yahoo Finance |
| Pydantic | 2.x | Data validation |
| OpenAI SDK | 2.35.1 | LLM provider |
| uvicorn | 0.46.0 | ASGI server |
| React | 19.2.3 | UI framework |
| Vite | 7.2.7 | Frontend build tool |
