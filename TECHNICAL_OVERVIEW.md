# Baboon Technologies — Technical Overview

> **Status: prototype.** This system works end to end and produces real analysis from real
> filings, but it is not production software. It has no security hardening, no cost controls,
> no observability, and several analytical simplifications that make its valuation output
> directional rather than decision-grade. Its answers are written by an LLM and can misreport the
> very tool results they are built from — nothing in the system checks them.
> Read [§17 Limitations](#17-limitations-and-known-risks)
> before drawing conclusions from anything it outputs, and before deploying it anywhere public.

This document describes how the system actually works as of the current `main`, and why it is
built the way it is. It is written for a developer who needs to change something and wants to
know which decisions are load-bearing.

Supersedes the architecture sections of `ARCHITECTURE.md`, `AGENTIC.md`, `STATUS.md`,
`PROJECT_REPORT.md`, and `FINAL_VERSION.md`, which describe four earlier architectures and are
retained only as history. `README2.md` remains accurate. `GitWorkflow.md` and `DEPLOYMENT.md`
remain in force (with the caveat in [§15](#15-configuration)).

---

## Table of Contents

1. [What the system does](#1-what-the-system-does)
2. [Stack](#2-stack)
3. [Repository layout](#3-repository-layout)
4. [Request lifecycle](#4-request-lifecycle)
5. [The agent graph](#5-the-agent-graph)
6. [Agent state](#6-agent-state)
7. [Data cache](#7-data-cache)
8. [Tool catalogue](#8-tool-catalogue)
9. [Prompt system](#9-prompt-system)
10. [Per-node LLM allocation](#10-per-node-llm-allocation)
11. [Financial data pipeline](#11-financial-data-pipeline)
12. [DCF engine](#12-dcf-engine)
13. [Web research pipeline](#13-web-research-pipeline)
14. [API, auth, and persistence](#14-api-auth-and-persistence)
15. [Configuration](#15-configuration)
16. [Design decisions and trade-offs](#16-design-decisions-and-trade-offs)
17. [Limitations and known risks](#17-limitations-and-known-risks)
18. [Making changes](#18-making-changes)
19. [What production would require](#19-what-production-would-require)

---

## 1. What the system does

A user asks a natural-language question about a public company. The system fetches that
company's SEC filings, market data, and sector assumptions; computes ratios, growth rates, a DCF
valuation, and peer comparables; optionally searches the web for qualitative context; and
synthesizes an investor-oriented written analysis, streamed back token by token.

The distinguishing property is that **the LLM never produces financial numbers**. It selects
which tools to call and interprets their output. Every figure in a response originates from a
deterministic Python function operating on fetched data. This is the core architectural
commitment and most other decisions follow from it.

What it does **not** guarantee is that the written answer reports those numbers faithfully. The
architecture controls where a figure comes from; nothing verifies that the prose matches it. See
[§17.8](#178-the-response-can-contradict-the-tools).

---

## 2. Stack

| Layer | Choice |
|---|---|
| Runtime | Python ≥ 3.11, dependency management via `uv` |
| API | FastAPI + Uvicorn |
| Agent | LangGraph `StateGraph`, `MemorySaver` checkpointer |
| LLM access | LangChain `init_chat_model` (provider-agnostic) |
| Data | SEC EDGAR via `edgartools`, Yahoo Finance via `yfinance`, FRED (DGS10), Damodaran (NYU Stern) |
| Web research | `ddgs` (DuckDuckGo) + `httpx` + `scrapy.Selector` |
| Validation | Pydantic v2 |
| Auth / persistence | Supabase Auth + Postgres, accessed over PostgREST with `httpx` |
| Frontend | React 19 + Vite 7, plain JSX, no state library |

Note: `backend/pyproject.toml` declares LangChain integration packages for ~12 providers
(Cohere, Fireworks, Vertex, Ollama, xAI, …). Only OpenAI and Anthropic are exercised by the
default configuration — see [§17.2](#172-llm-compatibility-is-unverified).

---

## 3. Repository layout

```
BaboonTechnologiesProject/
├── backend/
│   ├── pyproject.toml
│   ├── supabase/migrations/        SQL schema for auth, profiles, chats
│   ├── tests/unit/                 pytest suite (~70 tests, agent-focused)
│   └── src/backend/
│       ├── main.py                 FastAPI app + CORS
│       ├── core/
│       │   ├── config.py           Pydantic Settings from .env
│       │   └── llm.py              Per-node model construction
│       ├── api/
│       │   ├── routes.py           HTTP surface + error translation
│       │   ├── schemas.py          Request/response models
│       │   └── controllers/        agent.py, chats.py, companies.py
│       ├── auth/dependencies.py    Supabase bearer-token verification
│       ├── db/supabase.py          PostgREST client (service role)
│       ├── repositories/chats.py   Session and message persistence
│       ├── adapters/               edgar.py, yahoo_finance.py, fred.py, damodaran.py
│       ├── processing/
│       │   ├── schema.py           All Pydantic financial models
│       │   └── xbrl_map.py         XBRL concept → internal field mapping
│       ├── services/               financials, ratio, growth, dcf_engine,
│       │                           comparables, scrape, agent_service
│       ├── agent/
│       │   ├── graph.py            Node/edge wiring
│       │   ├── state.py            AgentState TypedDict
│       │   ├── constants.py        Recursion and scrape budgets
│       │   ├── prompts.py          All system prompts
│       │   ├── llm.py              Prompt assembly + context policy
│       │   ├── runtime.py          Invocation entrypoints
│       │   ├── messages.py         Message-history helpers
│       │   ├── nodes/              One file per node
│       │   ├── edges/              One file per conditional edge
│       │   ├── tools/              base, research, calculation, registry
│       │   ├── cache/              store, merge, catalog, base, schema
│       │   └── streaming/          Event stream for SSE/NDJSON
│       └── scripts/                Ad-hoc CLI scratch scripts (not part of the app)
└── frontend/src/
    ├── pages/                      Landing, Auth, Chat, Profile
    ├── components/                 Composer, MessageBubble, Sidebar, Navbar, backgrounds
    ├── api/client.js               Backend calls
    ├── auth/                       Supabase client + AuthProvider
    └── utils/reportExport.js       Response export
```

`scripts/` contains development scratch files (`dcf_draft.py`, `xbrl2.py`, `xbrl3.py`,
`etl_lean.py`, …). Nothing in the request path imports from it. Treat it as an attic.

---

## 4. Request lifecycle

```
Browser (React)
  │  POST /agent/chat/stream  { message, session_id?, thread_id?, recursion_limit? }
  ▼
FastAPI route  ── Depends(get_current_user) ──► Supabase Auth /auth/v1/user
  │
  ▼
controllers/agent.py
  │  resolve or create chat session (ownership-checked)
  │  persist the user message
  ▼
services/agent_service.py   ── lru_cache(1) ──► compiled LangGraph (built on first call)
  │
  ▼
agent/runtime.py            reads prior checkpoint for thread_id, seeds initial state
  │
  ▼
LangGraph execution ────────► adapters ──► SEC EDGAR / Yahoo / FRED / Damodaran / DuckDuckGo
  │                                          │
  │  NDJSON events: thread, thought, delta, done
  ▼
Browser renders streamed markdown; assistant message persisted on completion
```

Graph construction is lazy (`agent_service._agent()` is `lru_cache`d). There is no startup
warm-up, so the first request in any process pays for graph construction plus first-use imports.

---

## 5. The agent graph

Seven nodes, wired in `agent/graph.py`. All routing is done with `add_conditional_edges` and
functions in `agent/edges/` — nodes return state deltas, never routing commands.

```
START → router ─┬─(end)──────────────────────────────────► END
                │
                └─(plan_node)─► plan_node ─┬─► tools ──────┐
                                           ├─► scrape_node ─┤
                                           └─► response_node │
                                                             ▼
                                                        react_node
                                            ┌────────────────┴─────────────────┐
                                            │                                  │
                                     tools / scrape_node                response_node
                                            │                                  │
                                            └──────────────►──────────────┐    ▼
                                                                          │ judge_node
                                                                          │    │
                                                        revise ───────────┘    └─(end)─► END
```

| Node | Responsibility | Can call tools |
|---|---|---|
| `router` | Classifies the request. Routes to `plan_node` or answers directly (`end`). Sets `deep_plan`. | No |
| `plan_node` | Emits the first tool-call batch and writes `tool_guidance` for downstream nodes. | Yes |
| `tools` | Executes all non-scrape calls in two phases: research, then calculation. Writes `research_messages` / `calculated_messages` / `data_catalog`. | — |
| `scrape_node` | Expands a scrape topic into multiple queries, fetches and scores pages, dedupes into `scrape_history`. | — |
| `react_node` | Evaluates results after each round; decides whether more data is needed or the set is sufficient. | Yes |
| `response_node` | Synthesizes the final markdown answer from the cached data. | No |
| `judge_node` | Evaluates the response. Verdict `end` (release) or `revise` (loop back to `react_node` with `judge_rationale`). | No |

`route_after_react` uses LangGraph `Send` to fan out to `tools` and `scrape_node`
**in parallel** when the plan status is `needs_scrape_and_tools`.

### Recursion budgets

Defined in `agent/constants.py`:

```python
RECURSION_LIMIT = 12
REACT_LIMIT = round(RECURSION_LIMIT / 1.42)   # 8  (~70%)
JUDGE_LIMIT = RECURSION_LIMIT - REACT_LIMIT   # 4  (~30%)
```

Every loop is a paid LLM call, so both loops are independently capped. Two details matter when
changing these:

- Both nodes stop at `limit - 2`, not at `limit`. Effective ceilings are **6 react iterations**
  and **2 judge iterations**. The 2-step margin reserves room for the forced response path.
- When a budget runs out, the node sets `forced_response_due_to_recursion = True`. The response
  prompt reads this flag and is instructed to state that planning stopped early and the answer
  may be incomplete.
- `judge_node` can grant extra react iterations via `judge_react_extensions`, which
  `react_node` adds to its own limit.

The API also accepts a per-request `recursion_limit` (`ge=3, le=50`), passed through to
LangGraph as `recursion_limit * 1000` — the multiplier exists because LangGraph counts
individual graph steps while the agent's own budget counts node iterations.

---

## 6. Agent state

`AgentState` (`agent/state.py`) is a `TypedDict` checkpointed by `MemorySaver`, keyed by
`thread_id`. The fields that carry design weight:

| Field | Purpose |
|---|---|
| `messages` | Full append-only history including raw `ToolMessage`s. Audit trail. |
| `dialogue` | Human turns and final AI responses **only**. This is what `router`, `plan`, and `response` actually see. |
| `research_messages` | Results of research tools (external fetches), deduped by an `identifier` tuple. |
| `calculated_messages` | Results of calculation tools, deduped the same way. |
| `data_catalog` | Compact availability summary derived from the two lists above; what `plan`/`react` see instead of raw data. |
| `scrape_history` | Accumulated high-confidence scrape results across all rounds. |
| `deep_plan` | Whether the router chose the deep-analysis path. Persists across turns so the next router reads it as `previous_depth`. |
| `plan_status` | `needs_scrape_and_tools` \| `needs_scrape` \| `needs_tools` \| `ready_to_respond`. Consumed by conditional edges. |
| `query_count` | Turns processed this conversation. Drives cache retention. |
| `judge_rationale` | Judge critique, fed back into `react_node` on a revise loop. |

The `messages` / `dialogue` split is deliberate: without it, tool payloads accumulate in every
prompt and the context cost of turn *N* grows with everything fetched in turns 1..*N*−1.

> **Stale comment:** `state.py` documents `judge_verdict` as `"end" | "revise" | "gather_more"`,
> but `JudgeDecision` in `nodes/judge.py` is `Literal["end", "revise"]`. `gather_more` does not
> exist. Trust the Literal.

---

## 7. Data cache

**There is no database-backed cache.** `research_messages` and `calculated_messages` are plain
Python lists inside `AgentState`, persisted between turns by the checkpointer.

Earlier versions used a per-session DuckDB file. It was removed; `agent/cache/__init__.py` says
so explicitly. Documentation elsewhere in the repo still describes it — ignore that.

Every tool reads and writes through one primitive in `agent/cache/store.py`:

- **`find(messages, identifier)`** — linear scan for an entry matching an identifier tuple, e.g.
  `("financials", "AAPL")` or `("ratios", "AAPL", "liquidity")`. Both sides are coerced to
  tuples before comparison, because the checkpointer's serialization turns tuples into lists
  across a turn boundary. Skipping that coercion silently re-fetches everything on turn 2.
- **`upsert(messages, ...)`** — replace-or-append behind a `threading.Lock`. Tools run
  concurrently via `asyncio.to_thread`, so find-then-mutate has to be atomic.
- **`merge.merge_financials_data`** — the only real merge. `get_financials` can be called with
  non-overlapping spans across a conversation, so periods are unioned by fiscal year and
  metadata nulls coalesced. Every other tool does a plain replace.
- **`catalog.build_data_catalog`** — the availability summary handed to `plan`/`react`.
- **`catalog.purge`** — drops entries past their retention window: `FETCHED_KEEP = 3` cycles for
  research data (expensive to refetch), `CALCULATED_KEEP = 2` for calculated data (free to
  recompute).

`response_node` reads the two lists directly. There is no payload-rebuilding step.

Lists are conversation-scoped and hold at most a few dozen entries, so linear scan is cheaper
than maintaining an index. If a conversation could ever hold thousands of entries this would
need to change.

---

## 8. Tool catalogue

Tools live in `agent/tools/research.py` (external fetches) and `agent/tools/calculation.py`
(derived data). `agent/tools/registry.py` is the single registration point — the graph, prompts,
and streaming labels all read from it.

| Tool | Phase | Output |
|---|---|---|
| `get_financials` | research | Historical 10-K statements by ticker and span or explicit fiscal years |
| `get_market_data` | research | Price, beta, shares outstanding, market cap, risk-free rate |
| `get_sector_data` | research | Sector equity risk premium and long-term growth rate for a year |
| `scrape_web` | research | Web search + page scraping for qualitative context |
| `get_income_statement_growth_rates` | calculation | YoY growth, income statement |
| `get_balance_sheet_growth_rates` | calculation | YoY growth, balance sheet |
| `get_profitability_ratios` | calculation | Gross / EBIT / net margin |
| `get_liquidity_ratios` | calculation | Current, quick, cash ratio |
| `get_solvency_ratios` | calculation | D/E, debt-to-assets, interest coverage |
| `get_efficiency_ratios` | calculation | DSO, DIO, DPO |
| `run_dcf_valuation` | calculation | Full DCF — UFCF, WACC, terminal value, intrinsic value/share |
| `get_comps_valuation` | calculation | Peer multiples, with Damodaran sector fallback |

Two invariants worth preserving:

1. **`get_financials` returns raw statements only.** Every computed metric requires its own tool.
   This is what prevents the LLM from doing arithmetic on raw figures and presenting the result
   as a computed ratio.
2. **Calculation tools raise `CacheMissError` rather than fetching.** If the plan forgot to
   request financials before ratios, the failure is loud. Silently fetching would hide planning
   bugs and make tool ordering untestable.

`tools_node` runs research calls first, awaits them fully, then runs calculation calls — so
phase 2 always sees phase 1's writes. Within a phase, all calls run concurrently regardless of
ticker.

---

## 9. Prompt system

All prompts are Python string constants in `agent/prompts.py`. They are composed, not duplicated:

```python
plan_prompt      = _plan_prompt_base + _plan_prompt_standard_addendum
deep_plan_prompt = _plan_prompt_base + _plan_prompt_deep_addendum
```

The same base + standard/deep addendum pattern applies to `react` and `response`. `judge_prompt`
has two addenda (`judge_react_addendum`, `judge_response_addendum`) appended situationally.

`app_context` is the universal preamble injected into every node's system prompt: systemic
mental model, narrative skepticism, epistemic layering ([Fact] / [Assumption] / [Uncertainty]),
and the global data-integrity guardrails.

### Prompt assembly and context policy

`agent/llm.py` holds all "who sees what" policy in two dictionaries, so nodes only pass their
own name:

- **`_NODE_MESSAGES`** — which message history each node receives. `router`/`plan`/`response`
  get `dialogue`; `react` gets last human + current tool block; `judge` gets last human only;
  `scrape` gets none.
- **`_NODE_CONTEXT`** — which runtime fields go into the JSON context block. `current_year` is
  always included; everything else (`available_tools`, `cached_data_catalog`, `scrape_history`,
  `judge_rationale`, `previous_depth`, `forced_response_due_to_recursion`) is opt-in per node.

The system prompt is built as two content blocks: a **stable** block (`app_context` + node
prompt) and a **volatile** block (runtime JSON). When the node's provider is Anthropic, the
stable block gets `cache_control: ephemeral` so the prefix is cached across calls. Reordering
these blocks silently disables prompt caching.

Structured outputs use `with_structured_output(schema, method="function_calling")` with Pydantic
models (`RouterDecision`, `ToolCallSpec`, `ReactDecision`, `JudgeDecision`).

---

## 10. Per-node LLM allocation

Set in `core/llm.py`. Each node gets its own provider and model, overridable by
`<NODE>_LLM_PROVIDER` / `<NODE>_LLM_MODEL` environment variables. Temperature is fixed at 0.

| Node | Default | Reason |
|---|---|---|
| `router` | `openai` / `gpt-4.1` | Depth routing is high leverage — a false "deep" flag makes the whole graph slower and costlier |
| `plan` | `openai` / `gpt-4.1` | Tool selection, dependency coverage, scope control |
| `react` | `openai` / `gpt-4.1` | Tool-aware reasoning; decides whether collection is complete |
| `response` | `anthropic` / `claude-sonnet-4-6` | Highest-value node: financial synthesis and grounded interpretation |
| `judge` | `openai` / `gpt-4.1` | Bad critiques trigger revision loops, so the judge is not cheapened |
| `scrape` | `openai` / `gpt-5.4-mini` | Query design matters but must stay cost-controlled |

Models are constructed eagerly at import of `core.llm`, so an invalid provider string fails at
startup rather than mid-request.

---

## 11. Financial data pipeline

```
EDGAR 10-K (XBRL)  ─►  adapters/edgar.py  ─►  processing/xbrl_map.py  ─►  processing/schema.py
                                                (concept → field)        (Pydantic validation)
                                                                              │
Yahoo Finance ─► adapters/yahoo_finance.py ───────────────────────────────────┤
FRED DGS10    ─► adapters/fred.py ────────────────────────────────────────────┤
Damodaran     ─► adapters/damodaran.py ───────────────────────────────────────┤
                                                                              ▼
                                                              services/ (financials, ratio,
                                                              growth, dcf_engine, comparables)
                                                                              │
                                                                              ▼
                                                                    agent tools → cache
```

`adapters/edgar.py` wraps `edgartools`' `Company` and pulls the last *N* 10-K filings as a
combined `XBRLS` object. `processing/xbrl_map.py` translates XBRL concepts to internal field
names; `processing/schema.py` validates into `HistoricalFinancials` (a list of periods, each
with `income_statement`, `balance_sheet`, `cash_flow`).

Because everything downstream consumes Pydantic models rather than raw provider payloads, the
services and agent layers are source-agnostic. Swapping EDGAR for another provider means writing
one adapter that returns the same types.

---

## 12. DCF engine

`services/dcf_engine.py`, three stages:

**`build_assumptions(hf, md, sd)`** — derives six drivers by **averaging each ratio across all
available historical periods**: revenue growth, EBIT margin, tax rate, D&A / revenue,
capex / revenue, NWC / revenue. Tax rate is clamped to `[0.0, 0.6]` and defaults to `0.21`.

**`build_valuation_inputs(...)`** — assembles WACC inputs. Cost of debt is resolved through a
four-level fallback chain:

1. Income-statement interest expense ÷ (short-term + long-term debt)
2. Cash-flow-statement interest expense ÷ long-term debt
3. Back-calculated as `(EBIT − net income − tax expense) ÷ long-term debt`, positives only
4. `risk_free_rate + 150bps` — sets `falled_back_to_risk_free_rate = True`

That flag propagates to `DCFOutput` and the response prompt is instructed to state it and treat
intrinsic value as directional whenever it is set.

WACC and its components are Pydantic `computed_field` properties on `ValuationInputs`:
cost of equity = CAPM (`rf + β × ERP`); weights from market cap and total debt.

**`run_dcf(...)`** — projects revenue → EBIT/EBIAT → D&A and capex → ΔNWC → UFCF for 5 years,
discounts at WACC, adds a Gordon Growth terminal value, bridges to equity
(`EV − total debt + cash`), and divides by shares outstanding.

See [§17.1](#171-the-dcf-is-structurally-simplified) for what this model does not do.

---

## 13. Web research pipeline

`scrape_node` expands a research topic into multiple queries and calls
`services/scrape.py::search_and_scrape_async` for each. That function:

1. Searches DuckDuckGo via `ddgs` (synchronous, so wrapped in `asyncio.to_thread`).
2. Filters out a default avoid-list (reddit, twitter/x, stocktwits, discord, quora, wikipedia)
   plus any caller-supplied patterns.
3. Fetches the surviving hits concurrently with `httpx`, 8s timeout, browser User-Agent.
4. Extracts text preferring `main p`, `article p`, `section p` over all `<p>`, falling back to
   the DuckDuckGo snippet when the page yields nothing.
5. Scores each result, truncates to a 600-character snippet, classifies the source type from URL
   patterns, and applies a `+0.1` bonus for preferred source types.

### The confidence score

`_confidence()` is a **lexical heuristic**, not a relevance model:

```python
query_score  = fraction of query words (len > 2) present in the text
goal_score   = fraction of research-goal words (len > 3) present in the text
length_score = min(len(text) / 2000, 1.0)

confidence = 0.45 × query_score + 0.35 × goal_score + 0.20 × length_score
```

Understand what this measures before relying on it — see
[§17.3](#173-the-scrape-confidence-score-does-not-measure-what-it-appears-to).

---

## 14. API, auth, and persistence

| Endpoint | Auth |
|---|---|
| `GET /`, `GET /health` | none |
| `GET /companies/{ticker}/financials\|market-data\|ratios\|growth\|dcf` | **none** |
| `GET /sector-data` | **none** |
| `POST /agent/chat` | required |
| `POST /agent/chat/stream` | required |
| `GET /me`, `PATCH /me` | required |
| `GET\|POST\|PATCH\|DELETE /chat/sessions[...]` | required |
| `GET /chat/sessions/{id}/messages` | required |

Auth (`auth/dependencies.py`) verifies the bearer token by calling Supabase's
`/auth/v1/user` on **every request** — no local JWT verification, no caching. Correct, but it
adds a network round trip to each call and makes the API unavailable when Supabase is
unreachable.

Chat sessions and messages are persisted to Supabase Postgres through a PostgREST client using
the service-role key (`db/supabase.py`). Session ownership is checked server-side via
`chats.require_session(current_user.id, session_id)`.

The streaming endpoint emits NDJSON events: `thread` (first, so the client can persist
continuity), then `thought` / `delta`, then `done`. The assistant message is persisted after the
stream completes.

**Agent state is not persisted.** `MemorySaver` is in-process memory. Chat *text* survives a
restart because it is in Postgres; the agent's tool results, scrape history, and internal
context do not.

---

## 15. Configuration

`core/config.py` (Pydantic `BaseSettings`, reads `backend/.env`).

Required: `EDGAR_USER_AGENT`, `FRED_API_KEY`, `OPENAI_API_KEY`.
Required in practice: `ANTHROPIC_API_KEY` — `response_node` defaults to Anthropic, so the agent
fails on its final step without it, even though `Settings` does not declare the field.
Required for auth/persistence: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`.

Optional: `CORS_ORIGINS` (comma-separated), `LLM_MAX_TOKENS`, and any
`<NODE>_LLM_PROVIDER` / `<NODE>_LLM_MODEL` override.

> `DEPLOYMENT.md` still documents a single global `LLM_PROVIDER` / `LLM_MODEL` pair. Those two
> fields still exist on `Settings` but nothing reads them — model selection is per-node. Follow
> the Render/Vercel steps in that file, but take the environment variables from here.

---

## 16. Design decisions and trade-offs

These are the choices that are expensive to reverse. If you are changing the system, read this
section first.

### 16.1 The LLM never computes numbers

Tools return computed values; the model selects tools and interprets output. Every figure is
traceable to a deterministic function.

*Trade-off:* every new metric requires a tool, a service function, and a registry entry.
Answering a question the tool set does not cover is impossible by design rather than
approximated. That rigidity is the point.

### 16.2 Explicit conditional edges, not `Command(goto=...)`

Routing lives in `agent/edges/`, separate from node logic in `agent/nodes/`. An earlier version
returned `Command(goto=...)` from nodes.

*Why:* graph topology is readable in one file (`graph.py`), routing is unit-testable without
running nodes, and LangGraph can render the topology. *Trade-off:* routing decisions are
expressed indirectly through `plan_status` rather than as a direct jump.

### 16.3 Cache in state, not in a database

Removed DuckDB in favor of plain lists in `AgentState`.

*Why:* the checkpointer already persists state per thread, so a second persistence mechanism
duplicated lifecycle management, connection handling, and schema DDL for data that never
outlives the conversation. It also removed per-tool connection open/close and write-conflict
serialization.

*Trade-off:* the cache dies with the process, cannot be shared across backend instances, and
cannot be queried. Acceptable only because it is conversation-scoped.

### 16.4 Two-phase tool execution

Research phase (external fetches) completes fully before the calculation phase (pure reads).

*Why:* it makes the dependency between "fetch financials" and "compute ratios from financials"
structural rather than a prompt instruction, so the LLM cannot order them wrongly. Within a
phase everything is concurrent.

*Trade-off:* a calculation that needs no research still waits for the research phase to finish.

### 16.5 `dialogue` separate from `messages`

Nodes see curated history, not raw tool output.

*Why:* prompt cost would otherwise grow with everything ever fetched in the conversation.
*Trade-off:* two histories to keep consistent; a node needing raw tool output must ask for it
explicitly.

### 16.6 A judge node instead of a longer response prompt

A separate node evaluates the response and can send it back for revision with a written critique.

*Why:* self-evaluation as a distinct step with its own model and prompt catches gaps that a
single-pass prompt does not. *Trade-off:* each revision doubles response cost and adds latency.
The judge is capped at 2 effective iterations for exactly this reason.

### 16.7 Depth bifurcation (`deep_plan`)

The router sets one boolean that selects standard vs deep prompts for plan, react, and response.

*Why:* "What was Apple's FY2024 revenue?" and "Build me an investment thesis on Apple" need
different breadth, tool budgets, and output structure — but the same machinery. One flag,
composed prompts, no duplicated logic. *Trade-off:* the router's classification is a
single point of failure for cost; a false "deep" makes a trivial question expensive.

### 16.8 Central tool registry

`registry.py` is the only place a tool is registered. Metadata (`group`, `route`, `phase`) is
attached there, not at the function.

*Why:* adding a tool touches one list. Graph routing, prompt tool descriptions, and streaming
labels all derive from it automatically.

### 16.9 `CacheMissError` instead of silent fetching

Covered in [§8](#8-tool-catalogue). Loud failure over convenient recovery, so planning bugs
surface in tests rather than in production cost.

### 16.10 Per-node model allocation

Each node names its own model. *Why:* the nodes have genuinely different requirements —
synthesis quality matters at `response`, latency and cost matter at `scrape`. *Trade-off:*
multiple provider accounts, multiple failure modes, and prompts that are implicitly tuned to
whatever model was configured when they were written ([§17.2](#172-llm-compatibility-is-unverified)).

### 16.11 Lazy graph construction

`agent_service._agent()` is `lru_cache(maxsize=1)`.

*Why:* imports of LangChain provider packages are slow; deferring them keeps process startup and
`/health` fast. *Trade-off:* the first chat request in each process absorbs that cost.

---

## 17. Limitations and known risks

This section is the reason the prototype label at the top of this document is there.

### 17.1 The DCF is structurally simplified

The model runs, but it is a teaching-grade DCF, not an analyst-grade one.

- **Flat single-scenario assumptions.** Each of the six drivers is one number — the arithmetic
  mean over available history — applied identically to all five projected years. No fade,
  no convergence to a terminal margin, no scenario or Monte Carlo analysis, no sensitivity
  table. A company mid-transition is projected as its own historical average.
- **Averaging is unweighted and outlier-sensitive.** Revenue growth is the mean of YoY changes.
  One anomalous year (an acquisition, a COVID year, a divestiture) moves the projection for all
  five years with no dampening.
- **Missing data silently becomes zero.** `build_assumptions` ends every derivation with
  `or 0.0`. If D&A cannot be extracted from the filings, `da_pct` is `0.0` and the model
  projects zero D&A, understating UFCF — it does not raise, and the output carries no flag
  distinguishing "genuinely zero" from "not found". This is a real observed failure: the Tesla
  test case in `Backend_agent_behavior_tests_.docx` produced a **negative** intrinsic value of
  −$15.42/share partly for this reason.
- **`wacc ≤ g` only warns.** `ValuationInputs.check_wacc` issues a `warnings.warn` and proceeds.
  The Gordon Growth denominator `(wacc − g)` then goes to zero or negative, producing an
  infinite, undefined, or negative terminal value that flows into the final number.
- **No guard on `shares_outstanding`.** `equity_value / inputs.shares_outstanding` will raise
  `ZeroDivisionError` if Yahoo returns zero or null.
- **Cost-of-debt level 3 is crude.** `EBIT − net income − tax expense` conflates interest
  expense with every other non-operating item.
- **Equity bridge is thin.** `EV − total debt + cash` only. No minority interest, no preferred
  stock, no investments in associates, no operating leases beyond what XBRL reports as debt.
  `total_cash` uses the `cash` field, not cash plus marketable securities.
- **Fixed 5-year horizon, no mid-year convention.**
- **Financial-sector companies are not handled.** A DCF on a bank is not meaningful, and nothing
  in the code blocks or flags it.

### 17.2 LLM compatibility is unverified

`pyproject.toml` declares LangChain packages for roughly a dozen providers. Only **OpenAI and
Anthropic** are exercised by the current default configuration; Groq was used previously and has
since been replaced.

Every other provider is untested with this codebase. Two failure modes are likely:

- **Structured output.** Every routing decision uses
  `with_structured_output(..., method="function_calling")`. Providers with weak or differently
  shaped function-calling support will fail schema validation, and there is no retry or fallback
  path — the node returns an error message into state.
- **Long-prompt instruction following.** The prompts in `prompts.py` run to hundreds of lines
  with base + addendum composition. Smaller models tend to follow the opening sections and lose
  later instructions, including the loop-prevention rules. There is no prompt-size adaptation.

Setting `<NODE>_LLM_PROVIDER` to something untested is a configuration change with no guardrail.
Verify structured output and instruction adherence before trusting it.

### 17.3 The scrape confidence score does not measure what it appears to

`_confidence()` is keyword overlap plus a length term. It cannot distinguish:

- **Relevance from repetition.** A page repeating query words in navigation, tags, or boilerplate
  scores as well as one that answers the question.
- **Content from length.** `length_score` is `min(len(text)/2000, 1.0)`, contributing up to 20%
  of the score. A long irrelevant page outscores a short precise one.
- **Correct from stale.** Nothing checks publication date. A 2019 article about a company scores
  identically to yesterday's filing.
- **Authoritative from not.** Source quality enters only as a `+0.1` bonus for a hardcoded list
  of domains and a hardcoded avoid-list. Everything else is `"web"`.

It is also **stopword-blind**: query words are filtered only by length (`> 2` chars,
`> 3` for goal words), so "with", "from", "that" count as evidence of relevance.

**Three thresholds disagree**, in three places, with no single source of truth:

| Value | Location | Effect |
|---|---|---|
| `0.25` | `services/scrape.py::_MIN_CONFIDENCE` | Results below this are discarded at fetch |
| `0.30` | `constants.py::SCRAPE_MIN_CONFIDENCE` | `scrape_node` filters again before storing |
| `0.60` | `prompts.py::app_context` | The LLM is told to treat anything below this as low-confidence |

So results scoring 0.30–0.60 are admitted to state and then flagged as unreliable in prose. The
number the user sees quoted in a response (`"[URL, confidence: 0.85]"`) is this heuristic — not
a calibrated probability, and it should not be read as one.

### 17.4 There is no security hardening

This is a prototype's threat model: essentially none. Concretely:

- **Unauthenticated data endpoints.** All six `/companies/*` and `/sector-data` routes require no
  auth. Anyone who can reach the host can trigger unbounded SEC EDGAR and Yahoo Finance fetches.
  That is an outbound-traffic and third-party-rate-limit liability, not just a data one.
- **No rate limiting anywhere.** No `slowapi`, no middleware, nothing. An authenticated user can
  issue unlimited agent requests, each costing real LLM spend at up to `recursion_limit = 50`.
- **Cross-user agent state leak via `thread_id`.** `thread_id` is client-supplied. `MemorySaver`
  is keyed by `thread_id` **globally**, with no user scoping. In `_resolve_session`, a request
  carrying another user's `thread_id` and no `session_id` finds no session for the caller, so it
  **creates a new session bound to that same `thread_id`** — and the subsequent
  `agent.aget_state(config)` loads the other user's checkpoint, including their dialogue history,
  into the new conversation's context. Chat *rows* are ownership-checked; the LangGraph
  checkpoint is not.
- **No prompt-injection defense.** Scraped web content goes into `scrape_history` and then into
  LLM context verbatim. A page crafted to contain instructions is indistinguishable from
  scraped fact at the prompt level. The `avoid` list filters social media, not adversarial text.
- **Internal errors are returned to clients.** `_raise_service_error` puts `str(exc)` and the
  exception class name into the HTTP response body, and the streaming error event does the same.
  Exception text leaks internal paths, library details, and query structure.
- **No secret hygiene.** The service-role key — which bypasses row-level security — is loaded
  into the same process that executes LLM-directed code paths. No key rotation, no scoping.
- **No input sanitization on the message body** beyond `min_length=1`. No length cap, so a
  multi-megabyte message is accepted and forwarded to the model.
- **No audit logging, no request tracing, no PII policy.**

### 17.5 Parts of the codebase were built exploratorily and show it

Written fast to find the shape of the problem, then kept. These are places where behavior may
not match intent:

- **34 `print()` calls in non-script runtime code** (`services/scrape.py`, `nodes/scrape.py`,
  `agent/runtime.py`, `services/growth.py`, `agent/main.py`). Debug output goes to stdout in
  production, bypassing the `logging` configuration used elsewhere.
- **Hardcoded ticker-specific workarounds.** `adapters/edgar.py::_FALLBACK_CONCEPTS` contains
  XBRL concepts annotated `# MSFT` and `# TSLA`. Extraction correctness for any company outside
  the ones that happened to be tested is unverified — and XBRL tagging varies widely by filer.
- **The `-2` margin in both recursion guards** (`react_count >= effective_react_limit - 2`) is
  unexplained. It makes the effective ceilings 6 and 2 rather than the 8 and 4 the constants
  suggest, which is easy to misread when tuning budgets.
- **Stale contracts in comments.** `state.py` documents a `judge_verdict` value that no longer
  exists ([§6](#6-agent-state)).
- **Dead configuration.** `Settings.llm_provider` / `llm_model` are read by nothing.
- **`scripts/` is an attic** — `dcf_draft.py`, `dcf_lean.py`, `dcf_variables.py`, `xbrl.py`,
  `xbrl2.py`, `xbrl3.py`, `etl.py`, `etl_lean.py`, `trace_min.py`. Overlapping, unversioned,
  unreferenced by the app. Do not treat any of it as documentation of current behavior.
- **`services/scrape.py::search_and_scrape`** is a sync wrapper kept "for backwards
  compatibility" with no current caller.

Assume that anything in this list may have been validated on one company, on one code path, once.

### 17.6 Data coverage is narrower than the interface implies

- **10-K only.** No 10-Q, so no quarterly analysis and no data more recent than the last annual
  filing. A question about the current quarter cannot be answered from filings.
- **US GAAP / SEC filers only.** No IFRS, no non-US companies, despite the UI accepting any
  ticker string.
- **No restatement or amendment handling.** `amendments=False` in the EDGAR filing query.
- **Sector data comes from Damodaran's annual dataset** — updated once a year, so ERP and
  long-term growth inputs can be up to twelve months stale.
- **Peer selection for comparables** is a heuristic; the Damodaran sector-multiple fallback is
  used when peers are unavailable, which materially changes what the "comparable" means.

### 17.7 Operational gaps

- **Single-process assumptions.** `MemorySaver` and `lru_cache(1)` are per-process. Running more
  than one backend instance means a user's follow-up question can land on an instance with no
  memory of the conversation. **The system cannot be horizontally scaled as written.**
- **No cost or token tracking.** Nothing counts tokens, attributes spend, or enforces a budget.
  The judge loop and the `deep_plan` path are the two ways a single question becomes expensive,
  and neither is metered.
- **No caching across conversations.** Two users asking about Apple in the same minute each
  trigger a full EDGAR fetch.
- **Thin test coverage.** ~70 tests, concentrated on agent cache evolution, graph behavior, and
  streaming. The DCF engine, ratio calculations, XBRL mapping, adapters, and the API layer have
  no direct unit coverage. The financial math — the part whose correctness the product depends
  on — is the least tested code in the repository.
- **No CI**, no linting gate, no type checking in the loop.
- **No graceful degradation.** If Yahoo Finance returns nothing, the DCF tool raises rather than
  returning a partial result with an explicit gap.

### 17.8 The response can contradict the tools

LLMs are stochastic. Temperature is fixed at 0, which reduces variance but does not eliminate it
and does nothing to make output faithful to its inputs.

The tool architecture ([§16.1](#161-the-llm-never-computes-numbers)) constrains where a number
comes from. It does not constrain what the final text says about it. `response_node` receives the
cached tool results as `data_payload` and writes free-form markdown. **Nothing compares the
figures in that text against the figures in the payload.** The model can transcribe a value
wrongly, attribute it to the wrong fiscal year, carry a ratio from one company into a sentence
about another, or state a conclusion the data does not support.

Two mechanisms are supposed to contain this, and neither is a check:

- **Prompt instruction.** `app_context` says "Never invent or extrapolate financial data" and
  requires `[Fact]` / `[Assumption]` / `[Uncertainty]` tagging. This is an instruction to a
  probabilistic system, not a constraint on it.
- **The judge node.** It reviews the response — but it cannot verify numbers. `_NODE_CONTEXT`
  grants `judge` only `cached_data_catalog`, and the catalog is an *availability* summary:
  which fiscal years exist, how many periods, booleans like `include_rfr`. The only real values
  that reach it are the DCF headline (intrinsic value per share, WACC) and the comparables value
  band. A wrong current ratio, a wrong growth rate, or a misattributed period gives the judge
  nothing to compare against. It can tell you data is *missing*; it cannot tell you a number is
  *wrong*.

Three further exposures:

- **Interpretation is unconstrained even when every figure is right.** Correct numbers can carry
  an unsupported causal story, and no part of the system evaluates the reasoning that connects
  them.
- **Scraped text shares the same context.** Web content enters `scrape_history` verbatim
  ([§17.4](#174-there-is-no-security-hardening)), so material that is merely wrong — not even
  adversarial — can be restated as fact, and its confidence score does not measure accuracy
  ([§17.3](#173-the-scrape-confidence-score-does-not-measure-what-it-appears-to)).
- **Risk scales down with model size.** The prompts are long and the guardrails live in them, so
  smaller models drop the rules first ([§17.2](#172-llm-compatibility-is-unverified)).

Practically: treat every figure in a response as requiring verification against the source
filing before it informs any decision. The system is a research accelerator, not a source of
record.

---

## 18. Making changes

### Adding a tool that derives from data already cached

1. Write the function in `agent/tools/calculation.py`. Accept
   `research_messages`, `calculated_messages`, and `cycle` as `Annotated[..., InjectedToolArg]`
   parameters — `tools_node` injects them at call time.
2. Read dependencies with `find(research_messages, ("financials", ticker))`. Raise
   `CacheMissError` if absent; do not fetch.
3. Write results with `upsert(...)`, choosing a stable `identifier` tuple and setting
   `data_source` to the real upstream provenance (`response_node` cites it verbatim).
4. Add one `ToolSpec` entry to `TOOL_SPECS` in `agent/tools/registry.py` with
   `phase=PHASE_CALCULATION`.

Nothing else changes. Prompts, routing, and streaming labels read from the registry.

### Adding a tool that fetches from a new external source

Steps 1–4 above, plus: write an adapter in `adapters/` returning a Pydantic model, add the model
to `processing/schema.py`, add a service function in `services/`, and register with
`phase=PHASE_RESEARCH`. If the data needs partial-overlap merging across calls, add a merge
function alongside `merge_financials_data` — otherwise `upsert` replaces.

### Changing which model a node uses

Set `<NODE>_LLM_PROVIDER` and `<NODE>_LLM_MODEL` in `backend/.env`. Nodes are `router`, `plan`,
`react`, `response`, `judge`, `scrape`. Read [§17.2](#172-llm-compatibility-is-unverified) first.

### Changing what a node can see

Edit `_NODE_CONTEXT` and `_NODE_MESSAGES` in `agent/llm.py`. Do not add context reads inside
node functions — keeping the policy in one place is what makes it auditable.

### Changing a prompt

Edit the `_base` constant to change behavior for both depths; edit the `_standard_addendum` or
`_deep_addendum` to change one. Preserve the two-block structure in `build_system_prompt` or
Anthropic prompt caching stops working.

### Adding a node

Add the function in `agent/nodes/`, export it from `nodes/__init__.py`, add its routing function
in `agent/edges/` if it branches, and wire both in `graph.py`. If it calls an LLM, add entries to
`_NODE_DEFAULTS` in `core/llm.py` and to `_NODE_MESSAGES` / `_NODE_CONTEXT` in `agent/llm.py`.

---

## 19. What production would require

Ordered by what would block a public deployment first.

1. **Authenticate `/companies/*` and `/sector-data`**, and add rate limiting on every route.
2. **Scope `thread_id` to the authenticated user** — derive it server-side from
   `(user_id, session_id)` rather than accepting it from the client ([§17.4](#174-there-is-no-security-hardening)).
3. **Stop returning exception text to clients.** Log internally, return opaque error codes.
4. **Replace `MemorySaver` with a persistent, shared checkpointer** (Postgres/Redis). Without
   this the service cannot run more than one instance.
5. **Add cost metering and per-user budgets** around the react and judge loops.
6. **Test the financial math.** Unit coverage for `dcf_engine`, `ratio`, `growth`, and
   `xbrl_map` against known-good fixtures, including the zero/missing-data paths.
7. **Make DCF failure modes explicit** — enforce `wacc > g`, guard `shares_outstanding`, and
   distinguish "value is zero" from "value not found" instead of `or 0.0`.
8. **Reconcile the response against tool output.** Extract the figures the model wrote and check
   them against the payload it was given, mechanically — not with another LLM. Today nothing
   catches a misreported number.
9. **Treat scraped content as untrusted input** at the prompt boundary.
10. **Replace the confidence heuristic** with something calibrated, or stop surfacing the number
    to users as if it were meaningful.
11. **Remove `print()` from runtime paths**, add structured logging, tracing, and CI.

Until at least items 1–4 are done, this should run only against trusted users in a controlled
environment.
