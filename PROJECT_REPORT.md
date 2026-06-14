# Baboon Technologies Project Report

## 1. Executive Summary

Baboon Technologies is a full-stack public-company research and valuation platform. It combines:

- A React/Vite web application for authentication, chat, profiles, session history, and report export.
- A FastAPI backend exposing financial-data, valuation, agent, profile, and chat APIs.
- SEC EDGAR ingestion and XBRL normalization for historical financial statements.
- Yahoo Finance, FRED, and Damodaran data for market and valuation inputs.
- Financial ratio, growth-rate, discounted cash flow (DCF), and comparable-company calculations.
- A LangGraph agent that routes requests, plans research, calls tools, caches data in a per-session DuckDB database, optionally searches the web, evaluates its own output through a judge node, and writes an investor-oriented response.
- Supabase Auth and Postgres persistence for users, profiles, chat sessions, and messages.

The repository contains a meaningful end-to-end product rather than a basic scaffold. Its strongest areas are the layered backend design, structured financial models, multi-model tool-backed agent, streaming user experience, and session persistence. Its known weaknesses include dependency on stable external data structures (particularly EDGAR/edgartools), simplistic DCF assumptions, and underdeveloped edge case handling for certain financial statement adapters — all of which are documented in detail in the Caveats section.

---

## 2. Product Purpose

The application is intended to let an authenticated user ask questions such as:

- How is a public company performing?
- What are its profitability, liquidity, solvency, and efficiency trends?
- How quickly are its financial statement items growing?
- What is its estimated intrinsic value under a DCF?
- How does it compare with selected peers or sector multiples?
- What recent events, guidance, or news affect the investment case?

The system answers through a conversational interface, using structured financial tools for quantitative claims and web research for qualitative or forward-looking context.

---

## 3. Setup

### 3.1 Prerequisites

- Python 3.11 or higher
- [`uv`](https://docs.astral.sh/uv/) (Python package manager)
- Node.js 18 or higher and npm

### 3.2 API Keys Required

Before running anything, obtain the following credentials:

| Credential | How to Obtain | Required |
|---|---|---|
| `EDGAR_USER_AGENT` | Your own email address. The SEC requires a valid contact email in the User-Agent header by policy — no account or registration needed. | Yes |
| `FRED_API_KEY` | Go to [fred.stlouisfed.org/docs/api/api_key.html](https://fred.stlouisfed.org/docs/api/api_key.html), create a free account, and request an API key from your account dashboard. | Yes |
| `OPENAI_API_KEY` | Go to [platform.openai.com](https://platform.openai.com), create an account, add billing under Settings → Billing, then generate a key under API Keys. | Yes (recommended) |
| `ANTHROPIC_API_KEY` | Go to [console.anthropic.com](https://console.anthropic.com), create an account, add a payment method, then generate a key under API Keys. | Yes (recommended) |
| `GROQ_API_KEY` | Go to [console.groq.com](https://console.groq.com), create a free account, and generate a key under API Keys. Free tier available. | Yes (recommended) |
| `XAI_API_KEY` | Go to [console.x.ai](https://console.x.ai), create an account, and generate a key. Compatibility with this codebase has not been fully verified — use with caution. | Optional |
| `SUPABASE_URL` | Create a project at [supabase.com](https://supabase.com). The URL is found in Project Settings → API → Project URL. | Full app only |
| `SUPABASE_ANON_KEY` | In the same Supabase project, go to Settings → API → `anon` public key. | Full app only |
| `SUPABASE_SERVICE_ROLE_KEY` | In the same Supabase project, go to Settings → API → `service_role` secret key. Keep this private and never expose it client-side. | Full app only |

**Confirmed compatible LLM providers:**

| Provider | Env Variable | Default node(s) | Notes |
|---|---|---|---|
| `openai` | `OPENAI_API_KEY` | router, plan, react, judge | Confirmed working. Used for structured-output nodes (routing, planning, tool selection, judging). |
| `anthropic` | `ANTHROPIC_API_KEY` | response | Confirmed working. Used for the reasoning-heavy response node — synthesizing all gathered data into the final investor analysis. Supports prompt caching. At the current scale, Anthropic models offer the best cost-to-reasoning-quality ratio for this task. |
| `groq` | `GROQ_API_KEY` | scrape | Confirmed working. Very fast and cheap; good for high-throughput or low-latency nodes. |
| `xai` | `XAI_API_KEY` | — | Not fully verified. May require additional LangChain configuration. |

Other providers listed in the `.env` comments (Google, Mistral, Cohere, Fireworks, Together, Ollama, HuggingFace, Bedrock) are supported by LangChain's `init_chat_model` interface in principle, but **have not been tested with this codebase**. Using them may require verifying that structured output via function calling works correctly for that provider, and that the model follows multi-step prompt instructions reliably. Do not assume compatibility without testing.

### 3.3 Folder Structure Clarification

The project contains two nested folders both named `backend`:

```
BaboonTechnologiesProject/
└── backend/                  ← OUTER backend — run commands from here, .env goes here
    ├── .env                  ← YOUR SECRETS FILE (create this)
    ├── pyproject.toml
    ├── uv.lock
    └── src/
        └── backend/          ← INNER backend — Python source code package
            ├── main.py
            ├── core/
            │   └── llm.py
            └── agent/
                └── ...
```

- The **outer** `backend/` folder is where you run `uv sync`, `uv run ...`, and where the `.env` file must be placed.
- The **inner** `backend/` folder (`backend/src/backend/`) is the Python package. You never place `.env` here and you do not run commands from here.

### 3.4 Creating the .env File

Create a file named `.env` directly inside the **outer** `backend/` folder — that is, at `BaboonTechnologiesProject/backend/.env` (the same directory as `pyproject.toml`). Use the following template:

```env
APP_NAME="Baboon Technologies API"
ENVIRONMENT="development"
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# SEC EDGAR — use your own email address
EDGAR_USER_AGENT=your_email@domain.com

# FRED (Federal Reserve Economic Data)
FRED_API_KEY=your_fred_key_here

# Supabase (required for full app with auth and chat persistence)
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_ANON_KEY=your_anon_key_here
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key_here

# LLM keys — include only those you intend to use
OPENAI_API_KEY=your_openai_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here
GROQ_API_KEY=your_groq_key_here

# Per-node model allocation — each agent node can use a different provider/model
ROUTER_LLM_PROVIDER=openai
ROUTER_LLM_MODEL=gpt-4.1

PLAN_LLM_PROVIDER=openai
PLAN_LLM_MODEL=gpt-4.1

REACT_LLM_PROVIDER=openai
REACT_LLM_MODEL=gpt-4.1

RESPONSE_LLM_PROVIDER=anthropic
RESPONSE_LLM_MODEL=claude-haiku-4-5-20251001

JUDGE_LLM_PROVIDER=openai
JUDGE_LLM_MODEL=gpt-4o-mini

SCRAPE_LLM_PROVIDER=groq
SCRAPE_LLM_MODEL=llama-3.3-70b-versatile

# Uncomment and increase if using large models such as Claude Opus or GPT-4 with long outputs
# LLM_MAX_TOKENS=16000

# LangSmith (optional — for tracing)
LANGSMITH_TRACING=false
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=your_langsmith_key
LANGSMITH_PROJECT="baboon-financial-analyst"
```

### 3.5 Running the Full Application

**Backend:**

```bash
cd backend
uv sync
uv run uvicorn backend.main:app --reload
```

**Frontend** (open a new terminal):

```bash
cd frontend
npm install
npm run dev
```

The frontend will be available at `http://localhost:5173`. It expects the backend at the URL configured in its `.env` (default `http://localhost:8000`).

### 3.6 Testing the Agent in the Terminal (Without Frontend)

To test the agent directly from the terminal without running the full application:

```bash
cd backend
uv run python src/backend/agent/main.py
```

The file being run is the outer `backend/src/backend/agent/main.py` — not any other `main.py` in the project. This is the CLI entry point for the agent, distinct from `backend/src/backend/main.py` which is the FastAPI application entry point.

This launches a CLI chatbot loop. Type any financial question and press Enter. Type `exit` to quit. The agent prints its response and a snapshot of the message history after each turn.

### 3.7 Switching LLM Providers or Models

Each agent node uses a separate model. The assignment is controlled in two places:

**Option A — via `.env` (no code change required, recommended):**

Each node reads its provider and model from environment variables at startup. The naming pattern is `{NODE}_LLM_PROVIDER` and `{NODE}_LLM_MODEL`. The six nodes are: `ROUTER`, `PLAN`, `REACT`, `RESPONSE`, `JUDGE`, `SCRAPE`.

```env
# Example: move the response node from Anthropic to OpenAI
RESPONSE_LLM_PROVIDER=openai
RESPONSE_LLM_MODEL=gpt-4o

# Example: move the scrape node from Groq to Anthropic
SCRAPE_LLM_PROVIDER=anthropic
SCRAPE_LLM_MODEL=claude-haiku-4-5-20251001
```

Restart the backend after changing `.env`. Models are initialized at import time in `core/llm.py` — changes take effect only after a restart.

**Option B — via `backend/src/backend/core/llm.py` (change the hardcoded defaults):**

The file `core/llm.py` defines `_NODE_DEFAULTS`, a dictionary that maps each node to its default provider and model. These defaults are used when the corresponding env vars are absent:

```python
_NODE_DEFAULTS: dict[str, tuple[str, str]] = {
    "router":   ("openai",    "gpt-4.1"),
    "plan":     ("openai",    "gpt-4.1"),
    "react":    ("openai",    "gpt-4.1"),
    "response": ("anthropic", "claude-haiku-4-5-20251001"),
    "judge":    ("openai",    "gpt-4o-mini"),
    "scrape":   ("groq",      "llama-3.3-70b-versatile"),
}
```

Change any entry here to permanently alter the default for that node. For example, to make Anthropic Claude the default for planning:

```python
"plan": ("anthropic", "claude-sonnet-4-6"),
```

The `model_provider` string passed to LangChain's `init_chat_model` must match exactly the provider name that LangChain recognizes. For confirmed providers these are `"openai"`, `"anthropic"`, and `"groq"`. Providing an unrecognized provider string will raise an error at startup.

**Important note on `LLM_MAX_TOKENS`:**

The `LLM_MAX_TOKENS` env variable is applied globally to every node. If you switch a node to a larger model capable of long outputs (e.g., Claude Opus, GPT-4 with extended context), uncomment and set this variable in `.env`:

```env
LLM_MAX_TOKENS=16000
```

Without it, large models may truncate their response mid-sentence at the provider's default output limit.

---

## 4. Repository Structure

```text
BaboonTechnologiesProject/
├── backend/
│   ├── .env                          Secrets and configuration (not committed)
│   ├── pyproject.toml                Python package and dependencies (uv)
│   ├── uv.lock                       Locked Python dependency graph
│   └── src/backend/
│       ├── main.py                   FastAPI application entry point
│       ├── core/
│       │   ├── config.py             Pydantic Settings — reads .env
│       │   └── llm.py                Per-node LangChain model initialization
│       ├── api/
│       │   ├── routes.py             HTTP endpoint registration
│       │   ├── schemas.py            Pydantic request/response schemas
│       │   └── controllers/
│       │       ├── agent.py          Agent and streaming route handlers
│       │       ├── chats.py          Chat session and message handlers
│       │       └── companies.py      Financial data endpoint handlers
│       ├── auth/
│       │   └── dependencies.py       Supabase bearer token verification
│       ├── db/
│       │   └── supabase.py           Supabase service-role REST client
│       ├── repositories/
│       │   └── chats.py              Chat session and message persistence
│       ├── adapters/
│       │   ├── edgar.py              SEC EDGAR XBRL wrapper
│       │   ├── yahoo_finance.py      Price, beta, shares, market cap
│       │   ├── fred.py               10-year Treasury yield (DGS10)
│       │   └── damodaran.py          NYU Stern Excel ERP and sector multiples
│       ├── processing/
│       │   ├── schema.py             Pydantic financial models and validators
│       │   └── xbrl_map.py           ~285 XBRL concept-to-field mappings
│       ├── services/
│       │   ├── financials.py         EDGAR ETL orchestrator with LRU cache
│       │   ├── growth.py             Year-over-year growth rate calculations
│       │   ├── ratio.py              Liquidity, solvency, profitability, efficiency ratios
│       │   ├── dcf_engine.py         Discounted cash flow valuation engine
│       │   ├── comparables.py        Peer and Damodaran comparable valuation
│       │   ├── scrape.py             DuckDuckGo search and async page scraping
│       │   └── agent_service.py      Agent invocation entry points for the API
│       ├── agent/
│       │   ├── main.py               CLI chatbot loop for terminal testing
│       │   ├── graph.py              LangGraph state machine (wires nodes and edges)
│       │   ├── state.py              AgentState TypedDict
│       │   ├── llm.py                LLM invocation helpers with Anthropic prompt caching
│       │   ├── prompts.py            System prompts for every node
│       │   ├── runtime.py            activate_agent_async entry points
│       │   ├── constants.py          RECURSION_LIMIT, REACT_LIMIT, JUDGE_LIMIT
│       │   ├── messages.py           Message history helpers
│       │   ├── nodes/
│       │   │   ├── router.py         Router node
│       │   │   ├── plan.py           Plan node
│       │   │   ├── tools.py          Tools node (concurrent execution)
│       │   │   ├── scrape.py         Scrape node (async web research)
│       │   │   ├── react.py          React node (tool result evaluation)
│       │   │   ├── response.py       Response node (final answer composition)
│       │   │   └── judge.py          Judge node (response quality evaluation)
│       │   ├── edges/
│       │   │   ├── after_router.py   Routes to plan_node or END
│       │   │   ├── after_plan.py     Routes to tools, scrape, or response
│       │   │   ├── after_react.py    Routes to tools, scrape, or response
│       │   │   └── after_judge.py    Routes to END or back to react (revise)
│       │   ├── tools/
│       │   │   ├── research.py       get_financials, get_market_data, get_sector_data, scrape_web
│       │   │   ├── calculation.py    Growth, ratio, DCF, and comps tools
│       │   │   ├── base.py           Shared tool helpers (log_cache_status)
│       │   │   └── registry.py       Tool registry (TOOLS_BY_NAME dict)
│       │   ├── cache/
│       │   │   ├── session.py        DuckDB session lifecycle and schema DDL
│       │   │   ├── financials.py     FinancialsCache
│       │   │   ├── market_data.py    MarketDataCache
│       │   │   ├── sector_data.py    SectorDataCache
│       │   │   ├── growth.py         GrowthCache
│       │   │   ├── ratios.py         RatiosCache
│       │   │   ├── dcf.py            DCFCache
│       │   │   ├── comparables.py    CompsCache
│       │   │   ├── catalog.py        build_data_catalog and build_data_payload
│       │   │   ├── base.py           CacheHelpers base class, serialization
│       │   │   └── schema.py         Cache key constants and subdomain labels
│       │   └── streaming/
│       │       ├── events.py         Streaming event type definitions
│       │       └── stream.py         NDJSON streaming helpers
│       └── scripts/                  CLI utilities and experimental code
├── frontend/
│   ├── src/
│   │   ├── App.jsx                   Main client state and routing
│   │   ├── api/client.js             Backend API and NDJSON streaming client
│   │   ├── auth/                     Supabase client and auth provider
│   │   ├── pages/                    Landing, auth, chat, and profile screens
│   │   ├── components/               Shared UI components
│   │   ├── utils/reportExport.js     HTML/PDF-style report export
│   │   └── styles.css                Application styling (light/dark themes)
│   ├── package.json
│   └── vercel.json
├── render.yaml                       Render backend deployment config
├── ARCHITECTURE.md
├── AGENTIC.md
├── DEPLOYMENT.md
├── README.md
├── Backend_agent_behavior_tests_.docx
└── PROJECT_REPORT.md
```

---

## 5. Technology Stack

### Frontend

- React 19
- Vite 7
- Supabase JavaScript client
- React Markdown and GitHub-flavored Markdown
- Lucide icons
- Plain CSS with light and dark themes

### Backend

- Python 3.11+
- FastAPI and Uvicorn
- Pydantic v2 and pydantic-settings
- LangChain and LangGraph
- Multiple LLM providers supported via LangChain (OpenAI, Anthropic, Groq, Google, etc.)
- DuckDB (per-session in-memory/temp-file agent cache)
- pandas
- edgartools (SEC EDGAR XBRL ingestion)
- yfinance
- FRED API via `requests`
- DuckDuckGo search, httpx, and Scrapy selectors (web scraping)

### Persistence and Hosting

- Supabase Auth
- Supabase Postgres through PostgREST
- Render configuration for the backend
- Vercel configuration for the frontend

---

## 6. Backend Architecture

The backend follows a layered design:

```text
HTTP route
  -> controller
  -> service or repository
  -> adapter / calculation / Supabase
  -> Pydantic response
```

### Application Entry Point

`backend/src/backend/main.py`:

- Loads environment variables.
- Creates the FastAPI application.
- Configures CORS from `CORS_ORIGINS`.
- Includes the central API router.

### Configuration and LLM

`core/config.py` defines required settings via Pydantic Settings reading from `backend/.env`.

`core/llm.py` initializes one LangChain chat model per agent node, using the `ROUTER_LLM_PROVIDER` / `ROUTER_LLM_MODEL` naming pattern. This allows each node (router, plan, react, response, judge, scrape) to use a different model and provider simultaneously.

---

## 7. API Layer

### Public Financial Endpoints

- `GET /`
- `GET /health`
- `GET /companies/{ticker}/financials`
- `GET /companies/{ticker}/market-data`
- `GET /companies/{ticker}/ratios`
- `GET /companies/{ticker}/growth`
- `GET /companies/{ticker}/dcf`
- `GET /sector-data`

Ticker inputs are normalized to uppercase in the company controller.

### Authenticated Endpoints

- `POST /agent/chat`
- `POST /agent/chat/stream`
- `GET /me`
- `PATCH /me`
- `GET /chat/sessions`
- `POST /chat/sessions`
- `PATCH /chat/sessions/{session_id}`
- `DELETE /chat/sessions/{session_id}`
- `GET /chat/sessions/{session_id}/messages`

The API verifies a Supabase bearer token before allowing agent, profile, or chat access.

### Error Handling

Routes normalize controller errors: `ValueError` becomes HTTP 400, other errors become HTTP 502, existing `HTTPException` values are preserved, and streaming errors are emitted as NDJSON `error` events.

---

## 8. External Data Adapters

### SEC EDGAR

`adapters/edgar.py` subclasses `edgar.Company` from the `edgartools` library. It fetches recent non-amended 10-K filings, builds combined XBRL data for the requested span, filters facts by statement type, removes abstract facts, deduplicates concept/period pairs (preferring totals and higher-level entries), and returns period-first dictionaries. It also extracts company metadata including CIK, SIC, industry, fiscal-year end, state, website, and phone.

### Yahoo Finance

`adapters/yahoo_finance.py` obtains current price, beta, shares outstanding, and market capitalization via `yfinance`.

### FRED

`adapters/fred.py` fetches the latest DGS10 10-year Treasury yield and converts it from a percentage to a decimal. The value is cached for the process lifetime.

### Damodaran

`adapters/damodaran.py` reads NYU Stern Excel datasets for implied equity risk premium, industry trailing P/E, EV/Sales, and Price/Sales. The loaded tables are cached in memory.

---

## 9. Financial Data Processing

### XBRL Mapping

`processing/xbrl_map.py` maps approximately 285 SEC XBRL concept names into a compact internal schema across four mappings: income statement, balance sheet, cash flow statement, and per-share data. Alternative concepts are ordered so the mapper can select the first available representation — essential because companies frequently use different accepted XBRL concepts for economically similar values.

### Pydantic Models

`processing/schema.py` defines the domain model: `CompanyMetadata`, `PerShare`, `IncomeStatement`, `BalanceSheet`, `CashFlowStatement`, `MarketData`, `SectorData`, `FinancialPeriod`, `HistoricalFinancials`, `ValuationInputs`, `Assumptions`, and `DCFOutput`.

Important computed fields include EBIAT, EBITDA, net working capital, free cash flow, cost of equity (CAPM), and WACC.

Validation favors warning and fallback behavior instead of rejecting imperfect filings. Examples include gross-profit reconciliation, tax-rate sanity, balance-sheet identity, and net-income reconciliation.

---

## 10. Financial Services

### Financial ETL

`services/financials.py` orchestrates EDGAR fetch → XBRL mapping → Pydantic model construction → period sorting → `HistoricalFinancials` assembly. It also maintains a 128-entry in-process LRU cache with per-ticker/span locks.

### Growth Rates

`services/growth.py` calculates year-over-year changes: `(current - previous) / abs(previous)`. The first period returns null growth values.

### Ratios

`services/ratio.py` calculates liquidity (current, quick, cash), solvency (liabilities/equity, liabilities/assets, interest coverage), profitability (gross margin, EBIT margin, net margin), and efficiency (DSO, DIO, DPO) ratios. Zero denominators return `None`.

### Comparable-Company Valuation

`services/comparables.py` supports peer median P/E, EV/EBITDA, EV/Sales, P/S, and P/B, as well as Damodaran industry fallback based on SIC. Returns a low/mean/high valuation band, never a single-point estimate.

---

## 11. DCF Engine

`services/dcf_engine.py` implements the project's main intrinsic valuation model.

`build_assumptions()` averages historical revenue growth, EBIT margin, effective tax rate, D&A as a percentage of revenue, CapEx as a percentage of revenue, and net working capital as a percentage of revenue.

`run_dcf()`:
1. Projects revenue for five years using constant historical growth.
2. Applies a constant EBIT margin to derive EBIT.
3. Calculates tax and EBIAT.
4. Projects D&A and CapEx as percentages of revenue.
5. Calculates changes in net working capital.
6. Calculates unlevered free cash flow (UFCF = EBIAT + D&A − CapEx − ΔNWC).
7. Discounts annual UFCF at WACC.
8. Calculates Gordon Growth terminal value: `UFCF_final × (1 + g) / (WACC − g)`.
9. Adds discounted terminal value to discounted forecast cash flows.
10. Subtracts debt to reach equity value.
11. Divides by shares outstanding for intrinsic value per share.

The output includes detailed projections, discount factors, enterprise value, terminal value, terminal-value concentration, and fallback flags.

---

## 12. LangGraph Process

The agent is built as a LangGraph state machine. The compiled graph has seven nodes connected by conditional edges. Each node is an async function that reads from `AgentState`, calls an LLM or tool, and returns a partial state update.

### Graph Diagram

```
START
  │
  ▼
router ──────────────────────────────────────────────────────► END (direct answer)
  │
  ▼ (route = plan_node)
plan_node
  │
  ├──► tools ──────────────────────────────────────────────► react_node
  │                                                               │
  ├──► scrape_node ─────────────────────────────────────────► react_node
  │                                                               │
  ├──► tools + scrape_node (parallel) ────────────────────► react_node
  │                                                               │
  └──► response_node ◄────────────────────────────────────────── │
            │                                              ├──► tools
            ▼                                              ├──► scrape_node
         judge_node                                        └──► response_node
            │
            ├──► END (verdict = end)
            │
            └──► react_node (verdict = revise)
```

### Node Descriptions

**Router Node** (`nodes/router.py`)

The entry point for every user turn. It invokes the LLM with a structured output (`RouterDecision`) to decide between two paths: `end` (answer directly from context, no tools needed) or `plan_node` (financial analysis required). It also decides whether the request warrants a `Deep_Plan` (comprehensive multi-tool analysis) or a standard plan. Out-of-scope questions receive a direct redirect response here without ever entering the planning flow. The router also manages the per-session query cycle counter and triggers cache purge every 5 cycles.

**Plan Node** (`nodes/plan.py`)

Generates the initial tool-call batch. The LLM fills a `PlanDecision` structure containing a rationale and a list of `ToolCallSpec` entries. It selects from the available tools registered in `TOOLS_BY_NAME` and uses the appropriate system prompt (`plan_prompt` for standard, `deep_plan_prompt` for deep analysis). Based on whether tool calls include `scrape_web`, non-scrape tools, or both, it sets `plan_status` so the conditional edge routes to the correct node(s).

**Tools Node** (`nodes/tools.py`)

Executes all non-scrape tool calls from the plan message. Calls are grouped by ticker; groups run concurrently via `asyncio.gather` while calls within the same ticker group run sequentially to avoid DuckDB write conflicts. Each tool receives the `session_id` injected at call time, opens its own DuckDB connection, writes results, and closes the connection. After all tools finish, the node reads back a compact data catalog from DuckDB and stores it in state.

**Scrape Node** (`nodes/scrape.py`)

Handles `scrape_web` tool calls. For each scrape call, an LLM generates a `ScrapeDecision` with multiple targeted search queries, a research goal, preferred source types, and URLs to avoid. Each query runs `search_and_scrape_async` concurrently. Results are deduplicated by URL, ranked by confidence, and the top results are returned as a `ToolMessage`. High-confidence entries are also appended to `scrape_history` in state for the react and response nodes to read.

**React Node** (`nodes/react.py`)

Evaluates tool results and decides whether the data gathered so far is sufficient or whether additional tool calls are needed. It operates under a recursion budget (`REACT_LIMIT`, derived from `RECURSION_LIMIT`). If near the limit, it forces the process toward `response_node` to prevent infinite loops. When coming from a judge revision, it receives the judge's critique and the prior response to understand what gaps to address. It outputs another `ReactDecision` with optional additional tool calls or signals readiness to respond.

**Response Node** (`nodes/response.py`)

Composes the final user-facing answer. It opens the DuckDB session and calls `build_data_payload` to retrieve all cached data (financials, market data, growth, ratios, DCF, comparables, sector data) as a structured dictionary. This payload, together with the plan rationale and any judge critique (in revision mode), is injected into the LLM's system prompt. The LLM generates the final Markdown analysis. The response is stored in `current_response` in state so the judge can evaluate it.

**Judge Node** (`nodes/judge.py`)

Evaluates the response produced by `response_node` against the original user question. It operates under a `JUDGE_LIMIT` budget. The LLM fills a `JudgeDecision` with a verdict of either `end` (response is adequate) or `revise` (response has gaps). On `revise`, the edge routes back to `react_node`, and if `react_node` is near its own limit, the judge extends that limit by one iteration. On `end`, the response is re-appended to the message history as the final output.

### Conditional Edges

| Edge Source | Condition | Destination |
|---|---|---|
| `router` | `route == "plan_node"` | `plan_node` |
| `router` | `route == "end"` | END |
| `plan_node` | `needs_scrape_and_tools` | `tools` + `scrape_node` (parallel via `Send`) |
| `plan_node` | `needs_tools` | `tools` |
| `plan_node` | `needs_scrape` | `scrape_node` |
| `plan_node` | `ready_to_respond` | `response_node` |
| `tools` / `scrape_node` | (always) | `react_node` |
| `react_node` | `needs_tools` | `tools` |
| `react_node` | `needs_scrape` | `scrape_node` |
| `react_node` | `ready_to_respond` | `response_node` |
| `response_node` | (always) | `judge_node` |
| `judge_node` | `verdict == "end"` | END |
| `judge_node` | `verdict == "revise"` | `react_node` |

---

## 13. Data Flow

This section traces how values travel from external sources through the cache layer and into the final response.

### Step 1 — Adapters: External Data Ingestion

When a research tool is called (e.g., `get_financials("AAPL", span=5)`), the corresponding cache module checks the DuckDB session first. On a cache miss, it calls the adapter layer:

- **SEC EDGAR** (`adapters/edgar.py`): fetches the last N 10-K XBRL filings for the ticker. Returns raw `{period_end: {xbrl_concept: value}}` dictionaries for each statement type.
- **Yahoo Finance** (`adapters/yahoo_finance.py`): fetches current price, beta, shares outstanding, market cap.
- **FRED** (`adapters/fred.py`): fetches the DGS10 10-year Treasury yield; result is cached in the process for the server lifetime.
- **Damodaran** (`adapters/damodaran.py`): loads NYU Stern Excel files for equity risk premium and sector multiples; results are cached in the process.

### Step 2 — XBRL Mapping and Schema Validation

Raw EDGAR XBRL concept names are translated by `processing/xbrl_map.py` into compact internal field names using four mapping dictionaries (~285 concepts total). The normalized dictionaries are then passed to `processing/schema.py`, which constructs typed Pydantic models (`IncomeStatement`, `BalanceSheet`, `CashFlowStatement`, `PerShare`) for each fiscal period. Computed fields (EBIAT, EBITDA, FCF, NWC, WACC) are evaluated at construction time. Validators emit warnings rather than raising errors to tolerate imperfect filings.

### Step 3 — Services: Orchestration and Calculation

For raw data fetching:
- `services/financials.py` orchestrates EDGAR → XBRL mapping → Pydantic → `HistoricalFinancials`.
- `services/financials.py:get_market_data()` combines Yahoo and FRED.
- `services/financials.py:get_sector_data()` wraps Damodaran ERP and growth rate.

For derived calculations:
- `services/growth.py` computes year-over-year growth from `HistoricalFinancials`.
- `services/ratio.py` computes liquidity, solvency, profitability, and efficiency ratios.
- `services/dcf_engine.py` runs the full DCF from `HistoricalFinancials` + `MarketData` + `SectorData`.
- `services/comparables.py` computes peer or Damodaran-based valuation bands.

### Step 4 — DuckDB Cache: Per-Session Structured Storage

Every tool call opens a connection to the session's DuckDB file (a temporary file keyed by the LangGraph `thread_id`). The schema is derived automatically from the Pydantic models in `processing/schema.py` so columns stay in sync with the models.

Tables:
- `companies` — one row per ticker (metadata).
- `financials` — one row per `(ticker, fiscal_year)` — all statement fields flattened.
- `market_data` — one row per ticker (current snapshot).
- `sector_data` — one row per year (global Damodaran data).
- `growth_rates` — one row per `(ticker, statement)` with JSON payload.
- `ratios` — one row per `(ticker, ratio_type)` with JSON payload.
- `dcf` — one row per `(ticker, scenario)` with JSON payload.
- `comparables` — one row per `(ticker, method)` with JSON payload.

Each row carries a `cycle` integer (incremented by the router each turn) so `purge_old_data()` can delete stale rows based on configurable thresholds every 5 cycles: calculated data is purged aggressively (keep last 2 cycles), external searched data is retained longer (keep last 3 cycles).

### Step 5 — Data Catalog vs. Data Payload

Two functions in `cache/catalog.py` serve different consumers:

- `build_data_catalog(conn)` — produces a compact availability summary (which tickers have which data types, with coverage metadata). This is stored in `AgentState.data_catalog` and fed to the react and router nodes so they can see what data is already available without reading the full values.
- `build_data_payload(conn)` — produces the full detailed data for every ticker and all computed results. This is only called by `response_node`, which passes it to the LLM as `gathered_data` in the system prompt.

### Step 6 — Response Generation

The response node injects the full `build_data_payload` output into the LLM's context. The LLM synthesizes the structured data — multi-year financial statements, growth rates, ratios, DCF projections, and web research snippets — into a coherent investor-oriented Markdown response. The response is then evaluated by the judge node and, if approved, returned to the user.

### Data Flow Summary

```
External APIs (EDGAR, Yahoo, FRED, Damodaran, DuckDuckGo)
    │
    ▼  adapters/
Raw data (XBRL concepts, prices, rates, scraped text)
    │
    ▼  processing/ (XBRL mapping + Pydantic schema)
Validated HistoricalFinancials, MarketData, SectorData
    │
    ▼  services/ (ETL, growth, ratios, DCF, comps)
Derived calculations (growth rates, ratios, DCF output, comp bands)
    │
    ▼  agent/cache/ (DuckDB per-session tables)
Structured cache (companies, financials, market_data, growth_rates, ratios, dcf, comparables)
    │
    ├──► build_data_catalog ──► AgentState.data_catalog ──► react_node / router
    │                                                        (compact availability check)
    │
    └──► build_data_payload ──► response_node ──► LLM ──► Final Markdown response ──► User
                                (full data dump)
```

---

## 14. Agent Architecture Details

### State

`AgentState` (`agent/state.py`) contains:

- Append-only message history (`operator.add`).
- Static application context string.
- Current year for temporal grounding.
- Serialized tool catalogue for planner context.
- Router route and plan status.
- React and judge iteration counters.
- Judge verdict and judge rationale.
- Judge-granted react extensions.
- Recursion fallback flag.
- Session ID (DuckDB key).
- Data catalog (compact availability summary).
- Scrape history (running list of web research results).
- Tool guidance (plan rationale passed to response).
- Deep plan flag.
- Current response (latest response node output; overwritten per call).
- Query count (drives cache purge cycle).

### Streaming

The streaming layer translates graph activity into:
- `status` — short user-facing progress labels.
- `thought` — summarized execution steps.
- `delta` — final answer text chunks.

The API wraps these events as newline-delimited JSON (NDJSON) and adds `thread`, `done`, and `error` events.

---

## 15. Authentication and Persistence

### Authentication

The browser signs users in through Supabase. The Supabase access token is sent to FastAPI. FastAPI verifies it by calling `GET {SUPABASE_URL}/auth/v1/user`. The backend then uses a service-role key for database operations.

### Database Tables

- `profiles` — user metadata with foreign key to Supabase Auth users.
- `chat_sessions` — conversation sessions per user.
- `chat_messages` — individual messages per session.

Row-level security limits users to their own rows. A trigger creates a profile on signup.

### Chat Persistence

Every agent request: resolves or creates a chat session → persists user message → runs agent with session thread ID → persists assistant response → updates session metadata. Database preserves history across browser sessions. LangGraph's `MemorySaver` preserves agent state only inside the running backend process.

---

## 16. Frontend Architecture

`frontend/src/App.jsx` owns most client-side state: path, authentication, theme, API health, sessions, active session, messages, profile, composer draft, and streaming state. Routing uses `window.history`. Protected paths redirect unauthenticated users to login.

**Pages:** LandingPage, AuthPage, ChatPage, ProfilePage.

The client creates sessions on demand, adds optimistic messages, reads NDJSON incrementally, displays status labels and execution thoughts, appends streamed answer chunks, handles interruption, and reloads persisted messages when switching sessions.

Assistant output is rendered as Markdown. Report-like responses support copy, download as HTML, and print/save-as-PDF actions. Exported reports include branding, generation time, and a non-advice disclaimer.

---

## 17. Deployment Model

### Backend

`render.yaml` configures a Render Python service:

```bash
pip install uv && uv sync --frozen
uv run uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

### Frontend

Designed for Vercel: build command `npm run build`, output `dist`, SPA rewrite to `index.html`. Required browser variables: `VITE_API_BASE_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`.

---

## 18. Program Performance Observations

The following observations are based on functional testing conducted through the CLI, using `claude-haiku-4-5` as the response model.

### Routing Accuracy

The router reliably filters out-of-scope requests and casual messages without entering the planning path. Greetings, vague requests ("make me rich"), and off-topic questions receive direct router-level responses with zero tool calls. Questions about public companies consistently route to `plan_node`.

The deep-plan flag activates correctly for complex multi-dimensional questions (e.g., "When will Tesla go bankrupt?", "Make a ratio analysis for Tesla"), triggering more comprehensive tool selection and a higher sufficiency bar in the react node.

### Tool Selection and Parallelism

The planner selects tools with reasonable specificity:
- Single-year metric questions (e.g., "What was Apple's revenue for 2023?") trigger `get_financials` with `fiscal_years=[2023]`, fetching only the required period.
- Multi-company comparisons (e.g., "Compare Apple and Amazon's gross profit") trigger parallel `get_financials` calls for both tickers in a single plan.
- Comprehensive analyses trigger all relevant tools in the first plan call, with the react node adding supplementary tools (growth rates, DCF) on judge revision.

### React and Judge Interaction

The react node effectively decides when data is sufficient. Simple pointed questions typically require 1 react iteration and 1 judge iteration before approval. Complex analyses (multi-tool ratio + DCF + scraping) average 3–4 react iterations and 2 judge iterations. The judge's `revise` verdict is used constructively: in observed tests, judge revisions prompted the react node to add growth rates and DCF data that were absent from the initial plan, improving the depth of the final response.

Recursion limits engaged in one observed case (multi-turn context, AAPL FY2024 follow-up): the judge requested 3 revisions before the recursion guard forced a final response. The response was still accurate and complete despite the forced exit.

### Cache Effectiveness

Multi-turn conversations benefit from DuckDB caching. In a follow-up question about Apple's FY2024 revenue (after FY2023 was already fetched), the agent retrieved both years from cache rather than re-calling EDGAR, reducing latency and API cost.

### Response Quality and Accuracy

In verified tests against publicly available financials:
- Revenue figures for AAPL (FY2023: $383.3B, FY2024: $391.0B), TSLA, and AMZN matched reported financials.
- DCF valuations include explicit sensitivity caveats and flag data gaps (e.g., missing D&A in projections) rather than silently producing misleading outputs.
- The agent explicitly distinguishes between data from financial statements, market data sources, and web scraping, attributing each claim to its source.
- The judge node successfully pushed back on incomplete initial responses and the resulting revised responses included the missing dimensions (growth rates, DCF valuation) as expected.

### Observed Edge Cases

- **Missing D&A in DCF:** When depreciation/amortization data is unavailable in EDGAR filings, the DCF still runs but underestimates FCF. The agent flags this explicitly in the output.
- **Tax-inflated net income:** The agent correctly identified that TSLA's FY2023 net income was elevated by a $5B tax benefit and noted this in its assessment.
- **Negative DCF intrinsic value:** For companies with capex exceeding net income under deteriorating projections (TSLA), the model correctly outputs a negative intrinsic value and frames it as a directional signal rather than an absolute figure.

---

## 19. Caveats

### Dependency on External Data Structure (EDGAR / edgartools)

The XBRL normalization pipeline depends on the `edgartools` library and the SEC's EDGAR data structure remaining stable. The `xbrl_map.py` file maps approximately 285 specific XBRL concept names to internal fields. If EDGAR changes its taxonomy, if the edgartools library updates its internal API, or if a company files using non-standard extensions, the adapters will silently return `None` for affected fields or fail entirely. This dependency requires ongoing maintenance monitoring whenever edgartools releases a new version or the SEC updates its taxonomy.

### LLM Model Dependency and Cost

The agent routes different nodes to different LLM providers and models simultaneously. The choice of model directly affects response quality, inference latency, and cost per query. Smaller/faster models (Groq Llama for scraping, GPT-4o-mini for judging) reduce cost but may produce lower-quality structured outputs. Larger models (Claude Haiku for response, GPT-4.1 for planning) improve quality at higher cost. The system does not implement token counting, cost tracking, or budget guardrails. A poorly calibrated model choice — especially for the judge node, which can loop — can result in unexpectedly high API spend.

### Simplistic DCF Assumptions

The DCF engine uses simple historical averages for all projection inputs (constant growth rate, constant EBIT margin, constant D&A and CapEx percentages). It does not account for cyclicality, recent trend weighting, acquisitions, negative or outlier periods, or mean reversion. Terminal value frequently represents 70%+ of enterprise value, making results highly sensitive to the long-term growth assumption (hardcoded at 2.5%). Missing cash in the equity bridge (the model subtracts debt but does not add excess cash) systematically understates equity value. These limitations make the DCF output directionally useful but not a reliable standalone valuation.

### Incomplete Adapter Coverage for Edge Cases

Several financial statement adapters do not handle edge cases gracefully:
- Companies that do not report all three standard statements (e.g., holding companies, REITs, special-purpose vehicles) will have missing fields that produce `None` values without clear user-facing warnings.
- Financial sector companies (banks, insurance) use non-standard balance sheet structures that the XBRL mappings only partially cover.
- Companies with fiscal years that do not align to standard calendar quarters may return unexpected period dates.

### Calculation Services Run on Python For-Loops

All ratio, growth, and DCF calculations iterate over lists and dictionaries using standard Python loops. For the typical 3–5 period span used in this application, performance is adequate. However, for larger spans, bulk analysis of many tickers, or future features requiring cross-sectional computation, replacing these loops with NumPy or pandas vectorized operations would substantially improve performance.

### Underdeveloped build_data_payload Function

`build_data_payload` dumps the entire DuckDB session into a single dictionary that is injected verbatim into the response node's LLM context. This includes all fields for all tickers, all fiscal years, and all computed results regardless of what the user asked. For a simple single-metric question, this means the LLM receives a large amount of irrelevant data in its context, increasing cost (prompt tokens) without improving response quality. A targeted payload builder that selects only relevant data based on the query would be more efficient.

### LLM_MAX_TOKENS Requirement for Large Models

The response node generates long Markdown analyses. When using large models such as Claude Opus or GPT-4 with extended context, the default output token limit may truncate the response mid-sentence. The `LLM_MAX_TOKENS` environment variable must be set to an appropriate value (e.g., `16000`) when using large models. This variable is commented out by default in the `.env` template and must be manually enabled.

### Embedded Loops as a Potential Cost Sink

The judge-react loop is bounded by `JUDGE_LIMIT` and `REACT_LIMIT` (both derived from `RECURSION_LIMIT = 12`), but the judge can extend the react limit on each revision cycle. If `RECURSION_LIMIT` is increased significantly (e.g., to 50+), a judge that consistently issues `revise` verdicts will trigger many additional LLM calls before the recursion guard activates. Each judge-react cycle involves at minimum two LLM calls (react + response) before the judge evaluates again. High recursion limits combined with aggressive judge prompts can turn a single user query into 20+ LLM calls.

### Hardcoded Scraping Validity Logic

The scrape node accepts results based on a confidence threshold (`SCRAPE_MIN_CONFIDENCE = 0.3`) computed by the scraping service. The confidence scoring is based on heuristic content matching, not actual source verification. There is no validation of publication date, source authority, or factual accuracy. The agent may cite outdated web content or low-quality sources with confidence equal to that of authoritative sources. Additionally, the scrape node does not maintain a list of validated domains or apply source-type filtering beyond what the LLM optionally specifies in `preferred_source_types`.

---

## 20. Main Strengths

1. Clear separation between adapters, processing, services, API, agent, and persistence.
2. Structured Pydantic financial models instead of loosely shaped dictionaries throughout the application.
3. Dedicated tools for calculations, reducing the risk of the LLM inventing formulas.
4. Per-session DuckDB cache with cycle-based purging, eliminating redundant external API calls within a conversation.
5. Per-node model allocation, allowing cost/quality trade-offs at each stage of the agent pipeline.
6. Concurrent execution for multi-company and multi-tool analysis.
7. Judge node that actively evaluates response quality and requests revisions with specific critique.
8. Good streaming UX with progress labels, execution thoughts, and partial answer delivery.
9. Authenticated, user-scoped chat persistence across sessions.
10. Practical report rendering and export with branding and non-advice disclaimer.

---

## 21. How to Integrate an Additional Tool

The agent is designed to make adding a new tool straightforward. The actual number of steps depends on what kind of tool you are adding. There are two distinct paths:

- **Path A — New calculation over existing cached data** (e.g., a new ratio, a new derived metric): 3 steps. The cache infrastructure already exists; you only need to write the tool function, register it, and update the prompts.
- **Path B — New external data source** (e.g., insider trading activity, bond yield spreads, ESG scores): 6–7 steps. You need to build the full cache stack in addition to the tool function and registration.

Choose the path that matches what you are adding. Do not follow Path B steps if an existing cache table can hold your data.

---

### Path A — New Calculation over Existing Cached Data

Use this path when the tool computes a new metric from data already stored in DuckDB (financials, market data, ratios, growth rates, DCF, or comparables). No new tables, no new cache classes, no changes to `session.py` or `catalog.py`.

**Step A1 — Implement the calculation in `agent/tools/calculation.py`.**

Add a `@tool`-decorated function. The function must accept `session_id: Annotated[str, InjectedToolArg] = ""` as its last argument — the tools node injects this at call time. Open a DuckDB connection, read from the existing cache, compute your result, write it back if needed, and close the connection.

```python
@tool
def get_custom_margin_analysis(
    ticker: str,
    session_id: Annotated[str, InjectedToolArg] = "",
) -> dict:
    """Calculate custom margin analysis from cached financials."""
    conn = open_connection(session_id)
    try:
        result, was_cached = RatiosCache.get_or_calculate(conn, ticker, session_id=session_id)
    finally:
        conn.close()
    return result
```

If the calculation requires raw financials, read from `FinancialsCache`. If it requires market data, read from `MarketDataCache`. All existing cache classes expose a `get_or_calculate` or `get_or_fetch` method that handles cache hit/miss transparently.

**Step A2 — Register the tool in `agent/tools/registry.py`.**

Import your function at the top of the file and add a `ToolSpec` entry to `TOOL_SPECS`. Do not touch `TOOLS_BY_NAME` or `tools` directly — they are derived automatically from `TOOL_SPECS`:

```python
ToolSpec(
    tool=get_custom_margin_analysis,
    group="ratio",          # logical group for streaming labels
    route="ratios",         # route tag used by streaming events
    capability="Calculate custom margin analysis for a ticker over the latest fiscal-period span.",
    phase=PHASE_CALCULATION,
),
```

`TOOLS_BY_NAME` is built from `TOOL_SPECS` on import, and `plan_node` builds its `ToolName` enum from `TOOLS_BY_NAME` automatically. The LLM will see the new tool immediately after you add the spec.

**Step A3 — Update `agent/prompts.py`.**

Add a short entry for the new tool in `data_dictionary`. This is the shared reference that teaches every node how to interpret the tool's output. Follow the format of existing entries: state what the field measures, what it should and should not be used for, and any known edge cases or caveats.

```
get_custom_margin_analysis
  adjusted_margin    Adjusted operating margin after removing one-time charges. Use for:
                     trend analysis across periods. Not for: direct GAAP comparison —
                     adjustments are derived mechanically, not auditor-verified.
```

No changes to the plan, react, or response prompts are required if the tool fits naturally into an existing analytical category (e.g., a new ratio type). If the tool represents a genuinely new analytical dimension that the planner would not know to invoke, add a brief description to the plan prompt's tool list.

---

### Path B — New External Data Source

Use this path when the tool fetches data from an external API or database that is not already stored in any existing DuckDB table. You need to build the full cache stack before writing the tool function.

**Step B1 — Implement the data logic in `services/`.**

Create a new service file (or extend an existing one) in `backend/src/backend/services/`. The function should call the appropriate adapter and return a structured Python dictionary or Pydantic model.

```python
# services/insider_trades.py
def get_insider_trades(ticker: str, days: int = 90) -> dict:
    # Call your data source adapter, normalize, return structured data
    ...
```

**Step B2 — Create a cache class in `agent/cache/`.**

Create a new file (e.g., `agent/cache/insider_trades.py`). Follow the pattern of an existing cache — `agent/cache/ratios.py` is the closest model for JSON-payload tables. The class must inherit from `CacheHelpers` and implement at minimum:

- `get_or_calculate(conn, ticker, ...)` — checks DuckDB first, calls the service on miss, writes to DuckDB.
- `catalog_entry(conn, ticker)` — returns a compact availability summary dict for `build_data_catalog`.
- `payload_entry(conn, ticker)` — returns the full data dict for `build_data_payload`.

**Step B3 — Add the DuckDB table to `agent/cache/session.py`.**

Add a `CREATE TABLE IF NOT EXISTS` statement inside `_build_ddl()`. Use a JSON payload column for unstructured or variable-schema data, following the pattern of `growth_rates`, `ratios`, `dcf`, and `comparables`:

```python
"""
CREATE TABLE IF NOT EXISTS insider_trades (
    ticker       VARCHAR  NOT NULL,
    payload      JSON,
    span_days    INTEGER,
    cycle        INTEGER DEFAULT 0,
    last_updated TIMESTAMPTZ,
    PRIMARY KEY (ticker)
)
""",
```

Since sessions are ephemeral temporary files (one per conversation, deleted on session close), there is no migration concern — each new session creates a fresh database from the current DDL. Restart the backend after this change so new sessions pick up the updated schema.

**Step B4 — Register the cache in `agent/cache/__init__.py` and `catalog.py`.**

Export the new class from `__init__.py`. Then add explicit calls in both functions inside `catalog.py`:

- In `build_data_catalog`: add `your_cache.catalog_entry(conn, ticker)` inside the per-ticker loop, following the pattern of the existing entries.
- In `build_data_payload`: add `your_cache.payload_entry(conn, ticker)` inside the per-ticker loop.

> **Warning — silent failure point.** Both `build_data_catalog` and `build_data_payload` are manually enumerated. If you create the cache class and the DuckDB table but forget to add one of these two calls, the tool will execute and write data to DuckDB correctly, but the response node will never receive that data. There is no error — the data is simply absent from the LLM's context. Double-check that both functions in `catalog.py` have been updated.

**Step B5 — Create the LangChain tool in `agent/tools/research.py`.**

Add a `@tool`-decorated function. The function must accept `session_id: Annotated[str, InjectedToolArg] = ""` as its last argument:

```python
@tool
def get_insider_trades(
    ticker: str,
    days: int = 90,
    session_id: Annotated[str, InjectedToolArg] = "",
) -> dict:
    """Retrieve recent insider trading activity for a ticker."""
    conn = open_connection(session_id)
    try:
        result, was_cached = InsiderTradesCache.get_or_calculate(conn, ticker, days, session_id=session_id)
    finally:
        conn.close()
    log_cache_status("get_insider_trades", was_cached, ticker=ticker)
    return result
```

**Step B6 — Register the tool in `agent/tools/registry.py`.**

Import the function and add a `ToolSpec` entry to `TOOL_SPECS`. Use `phase=PHASE_RESEARCH` for external data sources:

```python
ToolSpec(
    tool=get_insider_trades,
    group="insider_trades",
    route="insider_trades",
    capability="Pull recent insider buying and selling activity for a ticker over a configurable day window.",
    phase=PHASE_RESEARCH,
),
```

As in Path A, do not edit `TOOLS_BY_NAME` or `tools` directly — they are derived from `TOOL_SPECS` automatically.

**Step B7 — Update `agent/prompts.py`.**

Add the new tool to `data_dictionary` with field-level guidance on what each returned value means, what it should and should not be used for, and any known data quality caveats. Additionally, add a brief description of the tool to the plan prompt's tool list so the planner knows when to invoke it. If the tool surfaces a genuinely new analytical dimension, add guidance to the response prompt on how to interpret and present it.

---

### Testing Either Path

Run the CLI entry point and ask a question that should trigger the new tool:

```bash
cd backend
uv run python src/backend/agent/main.py
```

Verify three things in order:
1. The plan node includes the new tool in its tool call list (check the printed rationale).
2. The tools node executes it without error (check logs for the cache status line).
3. The response node incorporates the result (the answer references the new data).

If step 3 fails but steps 1 and 2 succeed, the most likely cause is a missing entry in `build_data_payload` in `catalog.py`.

---

## 22. How to Connect Your Own Database

This section explains how to replace or supplement an existing external data source with a proprietary data feed — for example, an internal financial data API, a licensed market data provider, or an institutional research database.

The pattern is the same regardless of the data provider: create an adapter, plug it into the existing service layer, and the rest of the pipeline (cache, tools, agent) picks it up automatically.

**Step 1 — Create a new adapter in `backend/adapters/`.**

Write a new file (e.g., `adapters/bloomberg.py`) that wraps your data source's API or database client. The adapter's job is to translate between your source's data format and the internal field names used by `processing/schema.py`.

The adapter should:
- Accept a ticker and span (or other relevant parameters).
- Authenticate using credentials stored in `.env` (add them to `core/config.py`).
- Return data in the same format as the existing adapters: `{period_end: {internal_field: value}}` for time-series data, or a plain dict for snapshots.

```python
# adapters/bloomberg.py
from backend.core.config import settings

class ProprietaryDataAdapter:
    def __init__(self, ticker: str):
        self.ticker = ticker
        self.client = YourDataClient(token=settings.proprietary_api_key)

    def fetch_financials(self, span: int) -> dict:
        raw = self.client.get_financials(self.ticker, years=span)
        # Normalize to internal field names matching processing/schema.py
        return {period_end: normalize(row) for period_end, row in raw.items()}
```

**Step 2 — Add credentials to `core/config.py` and `backend/.env`.**

Add the new API key or connection string to the `Settings` class in `core/config.py` and add it to `backend/.env`:

```python
# core/config.py
bloomberg_api_key: str | None = None
```

```env
# backend/.env
BLOOMBERG_API_KEY=your_key_here
```

**Step 3 — Integrate the adapter into the relevant service in `backend/services/`.**

Find the service that orchestrates the data type you are replacing or supplementing. For example, to replace EDGAR financials with a proprietary data source:

- In `services/financials.py`, modify `get_financials()` to call your new adapter instead of (or in addition to) `Edgar`.
- If you want to fall back to EDGAR when the proprietary source is unavailable, implement a try/except fallback chain.

The Pydantic schema validation step in `processing/schema.py` and all downstream calculations (growth, ratios, DCF) are unaffected because they operate on the normalized internal field names, not on the adapter output directly.

**Step 4 — If the new source provides a new data type not already modeled, extend the schema.**

If your data source provides something genuinely new (e.g., ESG scores, credit default swap spreads, real-time order flow), add new Pydantic fields to the appropriate model in `processing/schema.py`, extend the XBRL mapping or create a new mapping file, and add a new DuckDB table in `agent/cache/session.py`.

**Step 5 — No changes are required to the agent layer.**

The agent, tool registry, cache system, and response node are all source-agnostic. They interact with data through the service functions and the DuckDB cache. As long as the service functions return the same Pydantic types, the entire agent pipeline operates identically regardless of the underlying data source.

**Step 6 — For real-time or streaming data sources, open a connection per tool call.**

The tools node calls each tool in a thread (`asyncio.to_thread`). Each tool should open and close its DuckDB connection within the call. If your data source requires a persistent connection (e.g., a database pool), initialize it as a module-level singleton in the adapter, following the pattern of `adapters/fred.py`'s process-lifetime cache.

---

## 23. Prompt Design

`agent/prompts.py` contains every system prompt used by the agent. This section explains how the prompts are structured, why they are designed the way they are, and where their limitations lie.

### Structure Overview

The file defines the following components:

| Component | Purpose |
|---|---|
| `data_dictionary` | Shared reference that teaches every node how to interpret each tool's output fields correctly |
| `app_context` | Universal BABON identity and behavior instructions — injected into every node's system prompt |
| `router_prompt` | Routing decision only: end vs. plan_node, standard vs. deep |
| `plan_prompt` / `deep_plan_prompt` | Initial tool-call generation for standard and deep analysis paths |
| `react_prompt` / `deep_react_prompt` | Gap-checking and supplementary tool calls after initial results |
| `response_prompt` / `deep_response_prompt` | Final answer composition for standard and deep analysis paths |
| `scrape_prompt` | Web research query generation and search strategy |
| `judge_prompt` | Analytical reasoning evaluation — approves or requests revision |
| `judge_react_addendum` | Appended to react prompt only during a revision cycle |
| `judge_response_addendum` | Appended to response prompt only during a revision cycle; carries the prior response and critique |

Shared rules that appear in multiple node prompts are defined once as private variables (`_DONT_PLAN`, `_TOOL_USE_RULES`, `_SPAN_RULES`, `_STOP_GATE`) and injected via f-strings. This keeps the rules at a single source of truth and prevents them from drifting out of sync.

### Design Rationale

**Divided workload instead of a monolithic prompt.**

Rather than a single large prompt that tries to instruct the model to plan, execute, react, judge, and respond all at once, each node receives only the instructions relevant to its specific function. The router prompt says only: decide the route. The plan prompt says only: call the right tools. The react prompt says only: check what is missing and call more tools if needed. The response prompt says only: interpret and present the data.

This division keeps each LLM call narrowly focused. The model is not trying to simultaneously reason about tool selection, data gaps, analytical interpretation, and response formatting in a single context — it does one thing at a time, which reduces instruction conflicts and improves reliability.

**Strict scope boundaries with explicit prohibitions.**

Each node prompt includes explicit negative instructions to prevent scope creep. The plan node receives: *"Do not answer the user. Do not analyze results. Do not summarize tool outputs. Do not invent financial data. Only call tools to gather information."* The judge receives: *"Structure, format, length, tone, conciseness, and presentation style are not your concern."* The react prompt states: *"If a tool's data is already in cached_data_catalog, do NOT call it again regardless of what the tool messages say."*

These prohibitions address real failure modes observed during development: a planner that starts answering the question instead of calling tools, a judge that flags formatting preferences rather than analytical flaws, or a react node that re-calls tools already present in the cache because it misread the tool message history. Each prohibition is a guard against a known pattern of model misbehavior.

**Standard and deep prompt pairs.**

Every major node — plan, react, and response — has two versions: a standard prompt and a deep prompt. The router selects between them by setting `deep_plan` in state. Deep prompts expand the sufficiency standard: the deep react prompt uses `_STOP_GATE`, a checklist of all analytical dimensions (profitability, liquidity, solvency, efficiency, growth, valuation, market context, qualitative context) that must all be covered before the node can signal readiness. The deep response prompt adds an analytical chain-of-reasoning framework, cross-dimensional reasoning examples, confidence labeling per conclusion, and a required open-questions section. Standard prompts are narrower and faster, designed for focused single-metric questions.

**The data dictionary as a shared interpretation layer.**

The `data_dictionary` string is injected into every node's system prompt via `build_system_prompt` in `agent/llm.py`. It does not describe what the tools do — that is covered by the tool schemas in `available_tools`. Instead, it instructs the model on how to interpret each field: what each metric should and should not be used for, what edge cases to flag, and what downstream bias a missing value introduces.

For example: `long_term_growth_rate` is documented as *"GDP-proxy terminal growth assumption (hardcoded at 2.5%). Use for: DCF terminal value only. Not for: company-specific growth forecast, sector growth trend, or analyst consensus. This is a model floor, not a prediction."* Without this instruction, a model would reasonably present the 2.5% figure as an industry or company growth expectation rather than a mechanical DCF floor.

**Temporal grounding built into routing and planning.**

Multiple prompts explicitly address `runtime_context.current_year` and instruct the model to treat it as the authoritative year rather than relying on training-data priors. The router prompt states: *"Any fiscal year before current_year has already ended and its actuals are retrievable via structured tools — never reject these requests as 'future' or 'unavailable' data."* This prevents a recurring model failure where the model refuses to fetch fiscal year data it believes has not yet occurred because its training cutoff predates the current year.

**Judge isolation from data.**

The judge node receives only the human messages and the current response text — not the full financial data payload. It is explicitly instructed: *"You do not have access to the underlying financial data — do not question whether figures are accurate. Trust that the tools provided correct data."* The judge evaluates only the quality of the reasoning and whether conclusions follow from the evidence cited in the response itself. This isolation prevents the judge from second-guessing data correctness (which it cannot verify) and keeps its evaluation focused purely on analytical logic.

**Revision cycle addenda.**

The `judge_react_addendum` and `judge_response_addendum` are not part of the base node prompts. They are appended by `react_node` and `response_node` only when `judge_verdict == "revise"`. This keeps the normal execution path clean and adds the revision context (the judge's critique, the prior response) only when it is actually needed. The response addendum includes a hard instruction: *"Write the entire response as if writing it for the first time... The user sees only what you write now — there is no prior version visible to them."* This prevents the model from producing patch-style responses that reference the previous version rather than rewriting it completely.

**Loop prevention in the react prompt.**

The react prompt includes explicit hard rules to prevent tool re-execution: the `data_catalog` is declared the ground truth over the tool message history, and re-calling a tool already in the catalog is prohibited regardless of what tool messages say. This addresses a real failure mode: after several tool messages accumulate in the history, models sometimes lose track of what has been called and begin repeating calls. The catalog-as-ground-truth instruction short-circuits this by giving the model a single authoritative source to check rather than parsing an accumulating list of tool messages.

---

### Weaknesses

**Prompts are still large.**

Even after dividing the workload, several prompts are long. The `deep_response_prompt` alone spans hundreds of lines covering cross-dimensional reasoning, analytical lenses, confidence labeling, red flags, and a required report structure. The `judge_prompt` is similarly detailed about what it must and must not evaluate. While smaller than a monolithic prompt, each node's total system context — `app_context` + `data_dictionary` + node prompt + runtime context — still amounts to a substantial token investment per LLM call.

**Smaller models may not follow multi-layered instructions reliably.**

The prompts are designed and validated against GPT-4.1, Claude Haiku, and Llama 3.3 70B. Smaller models (7B–13B parameter local models, lower-tier API options) tend to follow the first few paragraphs of a long prompt well but lose track of instructions placed later in the context. A small model used as the plan or react node may ignore the loop-prevention hard rules, produce unstructured output that fails the Pydantic structured-output schema, or conflate instructions from different sections. The system has no automatic fallback or prompt-size adaptation for smaller models — running them requires manual prompt simplification.

**Token degradation over long conversations.**

LLMs can show reduced instruction compliance in very long conversations where the system prompt is a small fraction of the total context. As the message history grows across many turns — especially in deep analysis sessions with multiple tool calls per turn — the proportion of context dedicated to the system prompt shrinks relative to the accumulated tool messages and conversation history. Late in a long conversation, the model may begin drifting away from the citation rules, the analytical framework, or the output format specified in the response prompt, because those instructions are far back in the context window relative to the recent conversational content.

**The data dictionary is injected into every node, including those that do not need it.**

`build_system_prompt` in `agent/llm.py` injects `data_dictionary` into every node's system prompt unconditionally. The router node, which only needs to decide a route, receives the full data dictionary about DCF field interpretations, efficiency ratio nuances, and scrape confidence thresholds — none of which it needs. This increases the token cost of every router call without adding any value. A node-aware injection policy (inject data dictionary only into react and response nodes) would reduce cost without affecting quality.

**The judge cannot catch tool selection failures.**

The judge evaluates only the reasoning in the final response. If the plan node selected the wrong tools or called tools with incorrect arguments, the judge has no mechanism to detect or correct this. It receives only the human question and the response text — it cannot compare the response against the raw financial data or verify that the right tools were called. A plan that selected `span=1` when the user asked for a 5-year trend, or that omitted DCF because it misclassified the question, would produce a response that may appear analytically sound to the judge even though it is built on incomplete data.

**Revision cycles grow prompt size.**

When the judge requests a revision, the `judge_response_addendum` appends the prior response text to the response node's system prompt so the model can see what it previously wrote. For long deep-analysis responses, this can add two to three thousand tokens to an already-large system prompt. In a second revision cycle, the prior response included is itself a revision — the accumulated prior response text grows with each cycle, potentially approaching the context limit of smaller models used for the response node.

---

## 24. Risks and Technical Debt

### Critical

1. **DCF denominator and required-input safety**

   `run_dcf()` does not reject `WACC <= terminal growth`, zero shares, empty periods, missing base revenue, or zero enterprise value. These cases can produce division errors, negative terminal values, or invalid ratios without clear user-facing error messages.

2. **In-memory agent checkpointing**

   LangGraph conversation state (MemorySaver) disappears on process restart and is not shared across multiple backend instances. Persisted chat text remains, but the agent cache and internal context (tool results, scrape history) do not survive a backend restart. Each new session after a restart starts from a clean DuckDB file even if the chat history in Supabase has prior context.

### High

3. **Requested recursion limit is not honored**

   The `agent_service.py` passes `recursion_limit` to `activate_agent_async`, but the graph-level recursion guard is managed internally by `RECURSION_LIMIT` in `constants.py`. These are currently not wired together consistently.

4. **Blocking work inside sync API routes**

   EDGAR, Yahoo, FRED, and Damodaran calls are synchronous. FastAPI runs sync routes in a thread pool, but long EDGAR downloads or Damodaran Excel fetches can still reduce capacity under load.

5. **External HTTP robustness**

   FRED uses `requests.get()` without explicit timeouts or `raise_for_status()`. Yahoo Finance error handling is thin. Retries, timeouts, and clearer provider-specific exceptions are needed for production reliability.

6. **Historical assumption quality in DCF**

   DCF assumptions use simple averages, constant growth, and constant margins. Outliers, negative denominators, acquisitions, cyclicality, and recent trend weighting are not handled.

7. **Missing cash in the equity bridge**

   The DCF subtracts debt but does not add excess cash. This can materially understate equity value.

### Medium

8. **Financial terminology**

   `debt_to_equity` and `debt_to_assets` use total liabilities, not interest-bearing debt. The labels can mislead users comparing against standard financial databases.

9. **Long-term growth is effectively global**

   `SectorData.long_term_growth_rate` defaults to 2.5%. It is not industry-specific despite being stored per sector year.

10. **Comparables integration**

    Comparables are agent-only, have no REST endpoint, and rely on broad SIC mapping and externally downloaded spreadsheets.

11. **Frontend state concentration**

    `App.jsx` handles routing, data loading, sessions, messaging, profile state, health checks, and streaming. This will become difficult to maintain as features grow.

---

## 25. Recommended Priorities

### Priority 1: Protect Financial Correctness

- Validate all required DCF inputs and reject or explicitly handle `WACC <= g`.
- Add cash to the enterprise-to-equity bridge.
- Clarify interest-bearing debt versus total liabilities in ratio labels.
- Add unit tests for every formula and edge case.
- Add DCF sensitivity tables for WACC and terminal growth.

### Priority 2: Stabilize the Agent

- Wire `recursion_limit` from the request through to the graph-level guard consistently.
- Persist LangGraph checkpoints in a durable shared store (e.g., a Postgres-backed checkpointer) so agent state survives restarts.
- Make `build_data_payload` query-aware to reduce unnecessary token usage.
- Test concurrent users and multi-ticker cache interaction under load.

### Priority 3: Improve Reliability

- Add timeouts, retries, and `raise_for_status()` to all HTTP adapter calls.
- Add a production startup smoke test.
- Confirm `uv sync --frozen` in a clean environment.
- Add a CI workflow for backend tests and frontend build.

### Priority 4: Reduce Documentation Drift

- Archive obsolete scripts or clearly mark experimental ones.
- Keep endpoint and tool catalogues in sync with the code.
- Remove stale imports and dead test assumptions.

### Priority 5: Improve Maintainability

- Split frontend state into routing, sessions, profile, and chat hooks.
- Introduce typed frontend API contracts.
- Add structured logging and request IDs.
- Add integration tests using mocked external providers.

---

## 26. Overall Assessment

The project has a strong product concept and a meaningfully complete implementation: it can ingest SEC filings, calculate financial analytics, run valuations, coordinate a multi-model LLM agent with a judge-react quality loop, stream results to the browser, authenticate users, persist chats, and export reports.

The architecture is well-structured and genuinely extensible — adding a new tool, swapping an LLM provider, or connecting a proprietary data source each requires changes in a small, well-defined location rather than scattered edits. The judge-react loop in particular demonstrates thoughtful design, enabling the agent to self-correct without user intervention.

The system should currently be considered a late prototype or early beta. Financial edge-case handling, DCF correctness guardrails, external HTTP robustness, recursion-limit consistency, and test coverage need attention before the output should be relied upon for repeatable valuation work.
