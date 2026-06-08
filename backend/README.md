# BABON Backend

Python FastAPI backend for the BABON financial analysis platform. Combines a LangGraph AI agent with SEC EDGAR data, Yahoo Finance, FRED, and web scraping to deliver deep public-company financial analysis.

## Stack

- **Runtime**: Python 3.11+, managed with `uv`
- **API**: FastAPI + Uvicorn
- **Agent**: LangGraph `StateGraph` with `MemorySaver` checkpointing
- **LLM**: OpenAI (configurable via `backend/core/llm.py`)
- **Data sources**: SEC EDGAR (10-K filings), Yahoo Finance (market data), FRED DGS10 (risk-free rate), Damodaran (sector assumptions), DuckDuckGo (web scraping)

## Run

```sh
uv run uvicorn backend.main:app --reload
```

Run the agent interactively from the terminal:

```sh
uv run python src/backend/agent/main.py
```

## Agent Architecture

The agent is a LangGraph `StateGraph` with five nodes:

```
START → router → plan_node ⟷ tools / scrape_node → response_node → END
```

| Node | Responsibility |
|------|---------------|
| `router` | Classifies the request: routes to `plan_node` or answers directly. Sets `Deep_Plan` flag. |
| `plan_node` | Iteratively calls tools. Uses `plan_prompt` (standard) or `deep_plan_prompt` (deep analysis). Loops until `ready_to_respond`. |
| `tools` | Executes all non-scrape tool calls in parallel, grouped by ticker. Writes results to `data_cache`. |
| `scrape_node` | Expands scrape topics into multi-query DuckDuckGo searches, fetches and scores pages, deduplicates results. |
| `response_node` | Synthesizes all gathered data into the final response. Uses `response_prompt` or `deep_response_prompt`. |

### Routing

The router produces a `RouterDecision` with:
- `route`: `"plan_node"` (tool-backed analysis) or `"end"` (direct answer / out-of-scope)
- `Deep_Plan`: `true` for broad, multi-step, judgment-heavy analysis (SWOT, 360, valuation, geopolitical scenarios, investment thesis); `false` for narrow factual questions
- `answer`: populated only when `route = "end"`

### Deep Plan vs Standard Plan

| | Standard (`plan_prompt`) | Deep (`deep_plan_prompt`) |
|-|--------------------------|--------------------------|
| Trigger | Narrow, focused questions | Open-ended, multi-dimensional, or scenario analysis |
| Stop condition | Data sufficiency check | Exhaustion-based: must pass a STOP GATE checklist covering all 11 tool categories |
| Response | `response_prompt` | `deep_response_prompt` with critical interpretation block |

### State (`AgentState`)

Key fields in `AgentState`:

| Field | Type | Description |
|-------|------|-------------|
| `messages` | `list[AnyMessage]` | Full conversation history (append-only) |
| `router_route` | `str` | Last routing decision |
| `plan_status` | `str` | `needs_tools`, `needs_scrape`, `needs_scrape_and_tools`, `ready_to_respond` |
| `plan_iterations` | `int` | Loop counter; node forces response near recursion limit |
| `data_cache` | `dict` | Per-ticker and global in-memory cache; merged across parallel tool calls |
| `data_catalog` | `dict` | Human-readable summary of what data has been gathered |
| `scrape_history` | `list[dict]` | Accumulated scrape results across all rounds |

## Tool Catalogue

All tools are defined in `src/backend/agent/tools.py` and receive `data_cache` as an injected argument to avoid redundant API calls.

| Tool | Phase | Description |
|------|-------|-------------|
| `get_financials` | research | Historical 10-K financial statements (income statement, balance sheet, cash flow) by ticker and span |
| `get_market_data` | research | Current price, beta, shares outstanding, market cap, and risk-free rate |
| `get_sector_data` | research | Sector-level equity risk premium and long-term growth rate for a given year |
| `get_income_statement_growth_rates` | calculation | YoY growth rates for income statement line items |
| `get_balance_sheet_growth_rates` | calculation | YoY growth rates for balance sheet line items |
| `get_profitability_ratios` | calculation | Gross margin, EBIT margin, net margin (not derivable from raw financials alone) |
| `get_liquidity_ratios` | calculation | Current ratio, quick ratio, cash ratio |
| `get_solvency_ratios` | calculation | Debt-to-equity, debt-to-assets, interest coverage |
| `get_efficiency_ratios` | calculation | DSO, DIO, DPO |
| `run_dcf_valuation` | calculation | Full DCF model: UFCF projections, WACC, terminal value, intrinsic value per share |
| `scrape_web` | research | DuckDuckGo search + page scraping for qualitative context, news, events |

`get_financials` returns **raw statements only**. Computed metrics (ratios, growth rates) always require their dedicated tools.

## DCF Engine

`src/backend/services/dcf_engine.py` builds valuation assumptions from historical financials:

- `build_assumptions`: derives revenue growth, EBIT margin, tax rate, D&A %, capex %, NWC % from 5-year averages
- `build_valuation_inputs`: computes WACC from CAPM (beta × ERP + risk-free rate), terminal value, equity value
- `run_dcf`: projects UFCF for 5 years, discounts to present, outputs intrinsic value per share and margin of safety vs current price

## API Endpoints

Base URL: `http://localhost:8000`

### Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Root — returns service name |
| `GET` | `/health` | Health check |
| `GET` | `/docs` | Swagger UI |

### Companies

| Method | Path | Params | Description |
|--------|------|--------|-------------|
| `GET` | `/companies/{ticker}/financials` | `span` (1–10, default 5) | Historical financial statements |
| `GET` | `/companies/{ticker}/market-data` | `include_rfr` (bool) | Market data + risk-free rate |
| `GET` | `/companies/{ticker}/ratios` | `span` | Liquidity, solvency, profitability, efficiency ratios |
| `GET` | `/companies/{ticker}/growth` | `span` (2–10) | YoY growth rates |
| `GET` | `/companies/{ticker}/dcf` | `span`, `year` | DCF valuation |
| `GET` | `/sector-data` | `year` | Equity risk premium and long-term growth rate |

### Agent

| Method | Path | Body | Description |
|--------|------|------|-------------|
| `POST` | `/agent/chat` | `AgentChatRequest` | Single-turn or multi-turn chat (blocking) |
| `POST` | `/agent/chat/stream` | `AgentChatRequest` | NDJSON streaming: emits `thought`, `status`, `delta`, `done`, and `error` events |

The streaming endpoint emits structured progress events as the agent works:
- `{"type": "thought", "content": "..."}` — agent reasoning step
- `{"type": "status", "text": "..."}` — short progress label (e.g. "Calculating ratios...")
- `{"type": "delta", "content": "..."}` — response token
- `{"type": "done"}` — stream complete
- `{"type": "thread", "thread_id": "..."}` — session thread ID for continuation

## Project Structure

```
src/backend/
├── agent/
│   ├── graph.py          # LangGraph StateGraph definition and all node logic
│   ├── state.py          # AgentState TypedDict
│   ├── tools.py          # LangChain tool definitions and TOOL_SPECS
│   ├── prompts.py        # All LLM prompts (router, plan, deep_plan, response, deep_response, scrape)
│   ├── cache.py          # In-memory data cache with get-or-fetch/calculate helpers
│   ├── cache_schema.py   # ToolSpec dataclass and tool metadata constants
│   └── main.py           # CLI entrypoint for interactive terminal testing
├── api/
│   ├── routes.py         # FastAPI router definitions
│   ├── schemas.py        # Pydantic request/response schemas
│   └── controllers/      # Business logic called by routes
├── services/
│   ├── financials.py     # Financial data fetching and normalization
│   ├── ratio.py          # Ratio calculation functions (liquidity, solvency, profitability, efficiency)
│   ├── growth.py         # YoY growth rate calculations
│   ├── dcf_engine.py     # DCF model: assumptions, WACC, UFCF projections, valuation
│   ├── scrape.py         # DuckDuckGo search + async page scraping with confidence scoring
│   └── agent_service.py  # Agent lifecycle management for the API
├── adapters/
│   ├── edgar.py          # SEC EDGAR API client (10-K XBRL data)
│   ├── yahoo_finance.py  # Yahoo Finance client (price, beta, market cap)
│   ├── fred.py           # FRED API client (DGS10 risk-free rate)
│   └── damodaran.py      # Damodaran dataset client (ERP, long-term growth)
├── processing/
│   ├── schema.py         # Core Pydantic models (HistoricalFinancials, MarketData, DCFOutput, etc.)
│   └── xbrl_map.py       # XBRL tag → schema field mapping for EDGAR normalization
└── core/
    ├── llm.py            # LLM client initialization
    └── config.py         # Environment configuration
```
