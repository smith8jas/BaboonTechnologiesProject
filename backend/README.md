# BABON Backend

Python FastAPI backend for the BABON financial analysis platform. Combines a LangGraph AI agent with SEC EDGAR data, Yahoo Finance, FRED, and web scraping to deliver deep public-company financial analysis.

## Stack

- **Runtime**: Python 3.11+, managed with `uv`
- **API**: FastAPI + Uvicorn
- **Agent**: LangGraph `StateGraph` with `MemorySaver` checkpointing
- **LLM**: per-node provider/model configured in `backend/core/llm.py` — OpenAI (`router`, `plan`, `react`, `judge`, `scrape`), Anthropic (`response`); override per node with `<NODE>_LLM_PROVIDER` / `<NODE>_LLM_MODEL` env vars
- **Data sources**: SEC EDGAR (10-K filings), Yahoo Finance (market data), FRED DGS10 (risk-free rate), Damodaran (sector assumptions), DuckDuckGo (web scraping)

## Run

```sh
uv run uvicorn backend.main:app --reload
```

Run the agent interactively from the terminal:

```sh
uv run python src/backend/agent/main.py
```

The compiled agent graph is built lazily, on the first chat request (`services/agent_service.py`'s `_agent()` is `lru_cache`d) — there is no startup warm-up, so the first message in any process pays for graph construction plus first-use import costs (e.g. EDGAR's XBRL standardization index).

## Agent Architecture

The agent is a LangGraph `StateGraph` with seven nodes:

```
START → router → plan_node → tools / scrape_node → react_node ⟷ tools / scrape_node
                                                          ↓
                                                   response_node → judge_node → END
                                                          ↑___________revise___________|
```

| Node | Responsibility |
|------|---------------|
| `router` | Classifies the request: routes to `plan_node` or answers directly. Sets the `deep_plan` flag. |
| `plan_node` | Generates the first tool-call batch and writes `tool_guidance` for later nodes. Uses `plan_prompt` (standard) or `deep_plan_prompt` (deep analysis). |
| `tools` | Executes all non-scrape tool calls in two phases — research (external fetches), then calculation (pure reads of research data) — fully concurrent within each phase. Writes `research_messages` / `calculated_messages` / `data_catalog`. |
| `scrape_node` | Expands scrape topics into multi-query searches, fetches and scores pages, deduplicates results into `scrape_history`. |
| `react_node` | Evaluates tool results after each round and decides whether more tools/scraping are needed or the data is sufficient. Only node (besides `plan_node`) that can request more tools. |
| `response_node` | Synthesizes `research_messages` / `calculated_messages` into the final response. Uses `response_prompt` or `deep_response_prompt`. Cannot call tools. |
| `judge_node` | Evaluates the response for completeness; verdict is `"end"` (release to user) or `"revise"` (loop back to `react_node` with `judge_rationale`). |

Both `react_node` and `judge_node` have independent recursion guards (`REACT_LIMIT`, `JUDGE_LIMIT` in `agent/constants.py`, split from one shared `RECURSION_LIMIT`); either forces a response when its budget is nearly exhausted (`forced_response_due_to_recursion`).

### Routing

The router produces a `RouterDecision` with:
- `route`: `"plan_node"` (tool-backed analysis) or `"end"` (direct answer / out-of-scope)
- `Deep_Plan`: `true` for broad, multi-step, judgment-heavy analysis (valuation, deep profile, investment thesis); `false` for narrow factual questions
- `answer`: populated only when `route = "end"`

### Deep Plan vs Standard Plan

| | Standard (`plan_prompt`) | Deep (`deep_plan_prompt`) |
|-|--------------------------|--------------------------|
| Trigger | Narrow, focused questions | Open-ended, multi-dimensional, or valuation analysis |
| Response | `response_prompt` | `deep_response_prompt` — full institutional report structure with confidence tagging |

### State (`AgentState`)

Key fields in `AgentState` (`agent/state.py`):

| Field | Type | Description |
|-------|------|-------------|
| `messages` | `list[AnyMessage]` | Full conversation history, including raw tool messages (append-only; kept for auditability) |
| `dialogue` | `list[AnyMessage]` | Human turns and final AI responses only — no tool messages. What `router`/`plan`/`judge` actually see. |
| `router_route` / `plan_status` | `str` | Routing decisions consumed by the conditional edges |
| `react_iterations` / `judge_iterations` / `judge_react_extensions` | `int` | Loop counters and judge-granted extensions for the recursion guards |
| `research_messages` | `list[dict]` | Research-tool results (financials, market data, sector data, Damodaran fallback), deduped by an `identifier` tuple |
| `calculated_messages` | `list[dict]` | Calculation-tool results (ratios, growth, DCF, comparables), deduped the same way; always recomputed, never staleness-checked |
| `data_catalog` | `dict` | Lightweight availability summary built from the two lists above, for `plan_node`/`react_node` |
| `scrape_history` | `list[dict]` | Accumulated high-confidence scrape results across all rounds |
| `query_count` | `int` | Turns processed this conversation; drives `research_messages`/`calculated_messages` retention (`cache/catalog.py:purge`) |

## Cache Architecture

There is no database-backed cache. `research_messages` and `calculated_messages` are plain lists living in `AgentState`, persisted across turns by the graph's `MemorySaver` checkpointer. Every tool reads/writes through one shared primitive (`agent/cache/store.py`):

- `find(messages, identifier)` — linear scan for the entry matching an `identifier` tuple (e.g. `("financials", "AAPL")`, `("ratios", "AAPL", "liquidity")`). Identifiers are compared as tuples on both sides, since the checkpointer's serialization round-trip turns a tuple into a list between turns.
- `upsert(messages, ...)` — replace-or-append, behind a `threading.Lock` (tools run concurrently via `asyncio.to_thread`, so the find-then-mutate step has to be atomic to avoid duplicate/lost entries when two calls target the same identifier).
- `merge.py` — `merge_financials_data` is the one real merge function (periods unioned by fiscal year, metadata nulls coalesced), since `get_financials` can be called with non-overlapping spans across a conversation. Every other tool does a plain replace.
- `catalog.py` — `build_data_catalog` (summary for `plan_node`/`react_node`) and `purge` (drops entries past their retention window — research data kept longer than calculated data, since recomputing is free).

`response_node` reads `research_messages`/`calculated_messages` directly — there is no separate payload-rebuilding step.

## Tool Catalogue

Tools live in `agent/tools/research.py` (external fetches) and `agent/tools/calculation.py` (derived data); `agent/tools/registry.py` is the single place a new tool gets registered. Research tools run before calculation tools in `tools_node`; within each phase every call runs concurrently.

| Tool | Phase | Description |
|------|-------|-------------|
| `get_financials` | research | Historical 10-K financial statements (income statement, balance sheet, cash flow) by ticker and span or explicit fiscal years |
| `get_market_data` | research | Current price, beta, shares outstanding, market cap, and risk-free rate |
| `get_sector_data` | research | Sector-level equity risk premium and long-term growth rate for a given year |
| `scrape_web` | research | Web search + page scraping for qualitative context, news, events |
| `get_income_statement_growth_rates` | calculation | YoY growth rates for income statement line items |
| `get_balance_sheet_growth_rates` | calculation | YoY growth rates for balance sheet line items |
| `get_profitability_ratios` | calculation | Gross margin, EBIT margin, net margin |
| `get_liquidity_ratios` | calculation | Current ratio, quick ratio, cash ratio |
| `get_solvency_ratios` | calculation | Debt-to-equity, debt-to-assets, interest coverage |
| `get_efficiency_ratios` | calculation | DSO, DIO, DPO |
| `run_dcf_valuation` | calculation | Full DCF model: UFCF projections, WACC, terminal value, intrinsic value per share |
| `get_comps_valuation` | calculation | Peer multiple comparables, with a Damodaran sector-multiple fallback when peers are unavailable |

`get_financials` returns **raw statements only**. Computed metrics (ratios, growth, DCF, comparables) always require their dedicated tools, which raise `CacheMissError` rather than silently fetching if their research dependency is missing.

## DCF Engine

`src/backend/services/dcf_engine.py` builds valuation assumptions from historical financials:

- `build_assumptions`: derives revenue growth, EBIT margin, tax rate, D&A %, capex %, NWC % from historical averages
- `build_valuation_inputs`: computes WACC from CAPM (beta × ERP + risk-free rate), terminal value, equity value
- `run_dcf`: projects UFCF for 5 years, discounts to present, outputs intrinsic value per share

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
| `POST` | `/agent/chat/stream` | `AgentChatRequest` | NDJSON streaming: emits `thread`, `thought`, `status`, `delta`, `done`, and `error` events |

The streaming endpoint emits structured progress events as the agent works:
- `{"type": "thread", "thread_id": "...", "session_id": "..."}` — resolved identifiers, sent first so the client can persist continuity
- `{"type": "thought", "content": "..."}` — agent reasoning step
- `{"type": "status", "text": "..."}` — short progress label (e.g. "Calculating ratios...")
- `{"type": "delta", "content": "..."}` — response token
- `{"type": "done"}` — stream complete
- `{"type": "error", "message": "...", "error_type": "..."}` — surfaced on failure

### Auth & Chat Sessions

| Method | Path | Description |
|--------|------|-------------|
| `GET` / `PATCH` | `/me` | Read or update the authenticated user's profile |
| `GET` / `POST` | `/chat/sessions` | List or create persisted chat sessions |
| `PATCH` / `DELETE` | `/chat/sessions/{session_id}` | Update or delete a session |
| `GET` | `/chat/sessions/{session_id}/messages` | List persisted messages for a session |

## Project Structure

```
src/backend/
├── agent/
│   ├── graph.py          # Wires nodes and edges into the compiled StateGraph
│   ├── state.py           # AgentState TypedDict
│   ├── runtime.py         # initial_state, activate_agent_async, recursion-guard helpers
│   ├── messages.py        # dialogue / tool-block message-selection helpers
│   ├── llm.py              # invoke_llm / invoke_llm_structured, per-node context policy
│   ├── prompts.py          # All LLM prompts (router, plan, deep_plan, react, response, deep_response, scrape, judge)
│   ├── constants.py        # Recursion limits, scrape limits
│   ├── nodes/               # router, plan, tools, scrape, react, response, judge
│   ├── edges/                # after_router, after_plan, after_react, after_judge — conditional routing
│   ├── tools/
│   │   ├── base.py          # ToolSpec, phase constants, cache-status logging
│   │   ├── research.py     # External-fetch tools (financials, market data, sector data, scrape)
│   │   ├── calculation.py  # Derived-data tools (ratios, growth, DCF, comparables)
│   │   └── registry.py      # TOOL_SPECS — the single place to register a new tool
│   ├── cache/
│   │   ├── store.py         # find / upsert — the shared, lock-protected dedup primitive
│   │   ├── merge.py         # merge_financials_data — period-union + metadata coalesce
│   │   ├── catalog.py       # build_data_catalog / purge
│   │   ├── base.py          # CacheHelpers, CacheMissError, tool_content
│   │   └── schema.py        # Ratio subdomain constants, default DCF scenario
│   ├── streaming/            # activate_agent_stream(_async) / activate_agent_stream_events_async
│   └── main.py               # CLI entrypoint for interactive terminal testing
├── api/
│   ├── routes.py          # FastAPI route definitions
│   ├── schemas.py         # Pydantic request/response schemas
│   └── controllers/       # Business logic called by routes (agent, chats, companies)
├── auth/
│   └── dependencies.py    # Current-user resolution for protected routes
├── repositories/
│   └── chats.py            # Supabase-backed chat session/message persistence
├── services/
│   ├── financials.py      # Financial data fetching and normalization
│   ├── ratio.py            # Ratio calculation functions (liquidity, solvency, profitability, efficiency)
│   ├── growth.py           # YoY growth rate calculations
│   ├── dcf_engine.py        # DCF model: assumptions, WACC, UFCF projections, valuation
│   ├── comparables.py      # Peer multiple comparables and Damodaran sector-multiple fallback (pure functions)
│   ├── scrape.py            # Web search + async page scraping with confidence scoring
│   └── agent_service.py    # Lazily-built, lru_cached agent graph + chat/stream entrypoints for the API
├── adapters/
│   ├── edgar.py            # SEC EDGAR API client (10-K XBRL data)
│   ├── yahoo_finance.py    # Yahoo Finance client (price, beta, market cap)
│   ├── fred.py              # FRED API client (DGS10 risk-free rate)
│   └── damodaran.py         # Damodaran dataset client (ERP, long-term growth, sector multiples)
├── processing/
│   ├── schema.py            # Core Pydantic models (HistoricalFinancials, MarketData, DCFOutput, etc.)
│   └── xbrl_map.py          # XBRL tag → schema field mapping for EDGAR normalization
├── db/
│   └── supabase.py          # Supabase client setup
└── core/
    ├── llm.py                # Per-node LLM provider/model configuration
    └── config.py             # Environment configuration
```
