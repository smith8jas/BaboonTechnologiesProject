# Baboon Technologies Project Report

## 1. Executive Summary

Baboon Technologies is a full-stack public-company research and valuation platform. It combines:

- A React/Vite web application for authentication, chat, profiles, session history, and report export.
- A FastAPI backend exposing financial-data, valuation, agent, profile, and chat APIs.
- SEC EDGAR ingestion and XBRL normalization for historical financial statements.
- Yahoo Finance, FRED, and Damodaran data for market and valuation inputs.
- Financial ratio, growth-rate, discounted cash flow (DCF), and comparable-company calculations.
- A LangGraph agent that plans research, calls tools, caches data, optionally searches the web, and writes an investor-oriented response.
- Supabase Auth and Postgres persistence for users, profiles, chat sessions, and messages.

The repository contains a meaningful end-to-end product rather than a basic scaffold. Its strongest areas are the layered backend design, structured financial models, tool-backed agent, streaming user experience, and session persistence. Its main weaknesses are deployment-breaking import capitalization, stale tests and documentation, insufficient validation around DCF edge cases, and incomplete dependency reproducibility in the current local installation.

## 2. Product Purpose

The application is intended to let an authenticated user ask questions such as:

- How is a public company performing?
- What are its profitability, liquidity, solvency, and efficiency trends?
- How quickly are its financial statement items growing?
- What is its estimated intrinsic value under a DCF?
- How does it compare with selected peers or sector multiples?
- What recent events, guidance, or news affect the investment case?

The system answers through a conversational interface, using structured financial tools for quantitative claims and web research for qualitative or forward-looking context.

## 3. Technology Stack

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
- OpenAI or another configured LangChain chat-model provider
- pandas and NumPy
- edgartools
- yfinance
- FRED API
- DuckDuckGo search, httpx, and Scrapy selectors

### Persistence and Hosting

- Supabase Auth
- Supabase Postgres through PostgREST
- Render configuration for the backend
- Vercel configuration for the frontend

## 4. Repository Structure

```text
.
|-- backend/
|   |-- src/backend/
|   |   |-- main.py                 FastAPI application
|   |   |-- api/                    Routes, transport schemas, controllers
|   |   |-- auth/                   Supabase token verification
|   |   |-- db/                     Supabase service-role REST client
|   |   |-- repositories/           Profile and chat persistence
|   |   |-- adapters/               External financial-data clients
|   |   |-- processing/             XBRL mappings and Pydantic models
|   |   |-- services/               Financial calculations and orchestration
|   |   |-- Agent/                  LangGraph agent, tools, cache, prompts
|   |   |-- scripts/                Experimental and CLI utilities
|   |   `-- data/sic.csv            SIC-to-industry mapping
|   |-- supabase/migrations/         Database schema and profile changes
|   |-- tests/                       Backend tests
|   |-- pyproject.toml               Python package and dependencies
|   `-- uv.lock                      Locked Python dependency graph
|-- frontend/
|   |-- src/
|   |   |-- App.jsx                 Main client state and routing
|   |   |-- api/client.js           Backend API and NDJSON streaming client
|   |   |-- auth/                   Supabase client and auth provider
|   |   |-- pages/                  Landing, auth, chat, and profile screens
|   |   |-- components/             Shared UI components
|   |   |-- utils/reportExport.js   HTML/PDF-style report export
|   |   `-- styles.css              Application styling
|   |-- package.json
|   `-- vercel.json
|-- render.yaml
|-- README.md
|-- ARCHITECTURE.md
|-- AGENTIC.md
`-- DEPLOYMENT.md
```

## 5. Backend Architecture

The backend follows a mostly clean layered design:

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

The module imports all routes during startup. Because agent routes eventually initialize modules that depend on LLM configuration, environment correctness is important even when only non-agent endpoints are needed.

### Configuration and LLM

`core/config.py` defines required settings for:

- EDGAR identity
- FRED API key
- OpenAI API key
- LLM provider and model
- Supabase URL and keys
- CORS origins

`core/llm.py` uses LangChain's `init_chat_model()` with temperature zero. A global `CHAT_MODEL` is built at import time.

## 6. API Layer

### Public Financial Endpoints

- `GET /`
- `GET /health`
- `GET /companies/{ticker}/financials`
- `GET /companies/{ticker}/market-data`
- `GET /companies/{ticker}/ratios`
- `GET /companies/{ticker}/growth`
- `GET /companies/{ticker}/dcf`
- `GET /sector-data`

Ticker inputs are normalized to uppercase in the company controller. Query parameters constrain spans and years.

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

Routes normalize controller errors:

- `ValueError` becomes HTTP 400.
- Other service errors generally become HTTP 502.
- Existing `HTTPException` values are preserved.
- Streaming errors are emitted as NDJSON `error` events.

## 7. External Data Adapters

### SEC EDGAR

`adapters/edgar.py` subclasses `edgar.Company`.

It:

- Sets the SEC-required identity from configuration.
- Fetches recent non-amended 10-K filings.
- Builds combined XBRL data for the requested span.
- Filters facts by statement type.
- Removes abstract facts.
- Deduplicates concept/period pairs, preferring totals and higher-level entries.
- Returns period-first dictionaries.
- Extracts company metadata including CIK, SIC, industry, fiscal-year end, state, website, and phone.

### Yahoo Finance

`adapters/yahoo_finance.py` obtains:

- Current price
- Beta
- Shares outstanding
- Market capitalization

It wraps failures in `ValueError`.

### FRED

`adapters/fred.py` fetches the latest DGS10 10-year Treasury yield and converts it from a percentage to a decimal. The value is cached for the process lifetime.

### Damodaran

`adapters/damodaran.py` reads NYU Stern Excel datasets for:

- Implied equity risk premium
- Industry trailing P/E
- Industry EV/Sales
- Industry Price/Sales

The loaded tables are cached in memory.

## 8. Financial Data Processing

### XBRL Mapping

`processing/xbrl_map.py` maps the many possible SEC concept names into a compact internal schema. Separate mappings cover:

- Income statement
- Balance sheet
- Cash flow statement
- Per-share data

Alternative concepts are ordered so the mapper can select the first available representation. This is essential because companies frequently use different accepted XBRL concepts for economically similar values.

### Pydantic Models

`processing/schema.py` defines the domain model:

- `CompanyMetadata`
- `PerShare`
- `IncomeStatement`
- `BalanceSheet`
- `CashFlowStatement`
- `MarketData`
- `SectorData`
- `FinancialPeriod`
- `HistoricalFinancials`
- `ValuationInputs`
- `Assumptions`
- `DCFOutput`

Important computed fields include:

- EBIAT = EBIT - tax expense
- EBITDA = EBIT + depreciation expense
- Net working capital = current assets - current liabilities
- Free cash flow = CFO - CapEx
- Cost of equity = risk-free rate + beta x equity risk premium
- WACC from equity and debt weights

Validation favors warning and fallback behavior instead of rejecting imperfect filings. Examples include gross-profit reconciliation, tax-rate sanity, balance-sheet identity, and net-income reconciliation.

`HistoricalFinancials.to_dataframe()` converts a selected statement into a period-indexed pandas DataFrame.

## 9. Financial Services

### Financial ETL

`services/financials.py` performs:

1. EDGAR fetch.
2. XBRL concept mapping.
3. Per-period Pydantic model construction.
4. Fiscal-period sorting.
5. HistoricalFinancials assembly.

It also offers an in-process 128-entry LRU-style financials cache with a lock per ticker/span so concurrent identical requests do not duplicate EDGAR work.

Market data combines Yahoo data with the optional FRED rate. Sector data currently combines Damodaran ERP with a default 2.5% long-term growth rate from the schema.

### Growth Rates

`services/growth.py` calculates year-over-year changes:

```text
(current - previous) / abs(previous)
```

The first period is returned with null growth values. Both income-statement and balance-sheet fields are covered.

### Ratios

`services/ratio.py` calculates:

- Liquidity: current, quick, and cash ratios.
- Solvency: liabilities/equity, liabilities/assets, and interest coverage.
- Profitability: gross margin, EBIT margin, and net margin.
- Efficiency: DSO, DIO, and DPO.

Results are grouped by fiscal year. Zero denominators generally return `None`.

### Comparable-Company Valuation

`services/comparables.py` supports:

- Peer median P/E, EV/EBITDA, EV/Sales, P/S, and P/B.
- Implied target values per share.
- Low, mean, and high valuation bands.
- Damodaran industry fallback based on SIC.
- Special notes for financial-sector companies.

This service is exposed to the agent but not through a dedicated REST endpoint. It is newer and less integrated than the DCF path.

## 10. DCF Engine

`services/dcf_engine.py` implements the project's main intrinsic valuation model.

### Historical Assumptions

`build_assumptions()` averages historical:

- Revenue growth
- EBIT margin
- Effective tax rate
- D&A as a percentage of revenue
- CapEx as a percentage of revenue
- Net working capital as a percentage of revenue

The tax rate is constrained to 0%-60%. Missing values usually fall back to zero, except tax, which defaults to 21%.

### Valuation Inputs

`build_valuation_inputs()` calculates debt and cost of debt.

Cost-of-debt hierarchy:

1. Income-statement interest expense / long-term debt.
2. Cash-flow interest expense / long-term debt.
3. EBIT - net income - tax expense, divided by long-term debt.
4. Risk-free rate + 1.5% fallback.

CAPM cost of equity:

```text
risk-free rate + beta x equity risk premium
```

WACC:

```text
equity weight x cost of equity
+ debt weight x cost of debt x (1 - tax rate)
```

### Projection and Valuation

`run_dcf()`:

1. Projects revenue for five years using constant growth.
2. Applies a constant EBIT margin.
3. Calculates tax and EBIAT.
4. Projects D&A and CapEx as percentages of revenue.
5. Calculates changes in net working capital.
6. Calculates UFCF:

```text
EBIAT + D&A - CapEx - change in NWC
```

7. Discounts annual UFCF at WACC.
8. Calculates Gordon Growth terminal value:

```text
final-year UFCF x (1 + g) / (WACC - g)
```

9. Adds discounted terminal value to discounted forecast cash flows.
10. Subtracts debt to reach equity value.
11. Divides by shares outstanding for intrinsic value per share.

The output includes detailed projections, discount factors, enterprise value, terminal value, terminal-value concentration, and fallback flags.

## 11. Agent Architecture

The live agent code is in `backend/src/backend/Agent/`, although imports use `backend.agent`.

### State

`AgentState` contains:

- Append-only message history
- Static application context
- Current year
- Serialized tool catalogue
- Router and plan status
- Plan/react iteration counts
- Recursion fallback state
- Structured data cache
- Prompt-visible cache catalogue
- Web scrape history
- Planning guidance
- Previous depth selection

### Graph

The compiled graph uses a LangGraph `MemorySaver`:

```text
START
  -> router
     -> END for direct answers
     -> plan_node
        -> tools and/or scrape_node
           -> react_node
              -> more tools/scraping
              -> response_node
                 -> END
```

The router decides whether financial tools are needed and whether the request deserves a deep analysis.

The planner writes a rationale and emits LangChain tool calls.

The tools node:

- Groups calls by ticker.
- Runs ticker groups concurrently.
- Runs individual calls in worker threads.
- Gives each call a copy of the cache.
- Merges cache changes afterward.

The scrape node:

- Expands one topic into multiple research queries using structured LLM output.
- Searches DuckDuckGo.
- Fetches pages asynchronously.
- Extracts article text.
- Scores relevance.
- Deduplicates URLs.
- Stores sufficiently confident results.

The react node checks whether more dimensions are needed. Standard and deep prompts use different sufficiency standards.

The response node receives the full structured cache and writes the final Markdown analysis.

### Agent Tools

Research tools:

- `get_financials`
- `get_market_data`
- `get_sector_data`
- `scrape_web`

Calculation tools:

- Income-statement growth
- Balance-sheet growth
- Liquidity ratios
- Solvency ratios
- Profitability ratios
- Efficiency ratios
- DCF valuation
- Comparable-company valuation

### Agent Cache

The cache separates:

- Company data from global data.
- Externally searched data from calculated data.
- Financials, market data, growth, ratios, DCF scenarios, and comparables.

Calculated outputs carry dependency and coverage metadata. A compact data catalogue tells the planner what is already available, while a detailed payload is only sent to the final response node.

### Streaming

The agent streaming layer translates graph activity into:

- `status`: short user-facing progress.
- `thought`: summarized execution steps.
- `delta`: final answer text chunks.

The API wraps these events as newline-delimited JSON and adds `thread`, `done`, and `error` events.

## 12. Authentication and Persistence

### Authentication

The browser signs users in through Supabase. It sends the access token to FastAPI.

FastAPI verifies the token by calling:

```text
GET {SUPABASE_URL}/auth/v1/user
```

The backend then uses a service-role key for database operations.

### Database Tables

The migrations create:

- `profiles`
- `chat_sessions`
- `chat_messages`

The schema includes:

- Foreign keys to Supabase Auth users.
- Automatic timestamps.
- A trigger to create a profile after signup.
- Row-level-security policies limiting users to their own rows.
- Additional profile fields such as username, full name, age, role, company, and biography.

### Chat Persistence

Every agent request:

1. Resolves or creates a chat session.
2. Persists the user message.
3. Runs the agent using the session's thread ID.
4. Persists the assistant response.
5. Updates session metadata.

The database preserves chat history across browser sessions. LangGraph's `MemorySaver` preserves agent state only inside the running backend process.

## 13. Frontend Architecture

### Main Application

`frontend/src/App.jsx` owns most client-side state:

- Current path
- Authentication state
- Theme
- API health
- Sessions
- Active session
- Messages by session
- Profile
- Composer draft
- Streaming state

Routing is implemented with `window.history` rather than a routing library. Protected paths redirect unauthenticated users to login.

### Pages

- `LandingPage`: marketing and product introduction.
- `AuthPage`: sign-in and registration.
- `ChatPage`: session sidebar, messages, composer, status, theme, and account controls.
- `ProfilePage`: editable user profile.

### Chat Experience

The client:

- Creates sessions on demand.
- Adds optimistic user and assistant messages.
- Reads NDJSON incrementally.
- Displays status labels and execution thoughts.
- Appends streamed answer chunks.
- Handles stream interruption.
- Reloads persisted messages when switching sessions.

### Markdown and Report Export

Assistant output is rendered as Markdown. Report-like responses receive:

- Report styling
- Copy action
- Download as standalone HTML
- Print/browser-save-as-PDF action

The exported report includes branding, generation time, and a non-advice disclaimer.

## 14. Deployment Model

### Backend

`render.yaml` configures a Render Python service:

```text
pip install uv && uv sync --frozen
uv run uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

### Frontend

The frontend is designed for Vercel:

- Build command: `npm run build`
- Output: `dist`
- SPA rewrite to `index.html`

Required browser variables include:

- `VITE_API_BASE_URL`
- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`

## 15. Testing and Current Validation

The repository has agent behavior and streaming tests, but coverage is narrow. There are no substantial tests for:

- EDGAR mapping
- Financial schema validators
- Ratio formulas
- Growth calculations
- DCF formulas and edge cases
- Comparable valuation
- API routes
- Authentication and repository behavior
- Frontend components

Validation performed while preparing this report:

- Frontend production build: failed because the current `node_modules` installation does not contain `@supabase/supabase-js`, although it is declared in `package.json` and `package-lock.json`.
- Backend tests: could not complete because `uv` needed to download a missing transitive package and network access was unavailable.
- Existing graph tests appear stale: they import old module-level cache helpers that have moved into `FinancialsCache` methods.

## 16. Main Strengths

1. Clear separation between adapters, processing, services, API, agent, and persistence.
2. Structured Pydantic financial models instead of loosely shaped dictionaries throughout the application.
3. Dedicated tools for calculations, reducing the risk of the LLM inventing formulas.
4. Agent cache with period coverage and dependency metadata.
5. Concurrent execution for multi-company and multi-tool analysis.
6. Good streaming UX with progress labels and partial answer delivery.
7. Authenticated, user-scoped chat persistence.
8. Practical report rendering and export.
9. Explicit prompts about uncertainty, source quality, DCF sensitivity, and unsupported advice.

## 17. Risks and Technical Debt

### Critical

1. **Case-sensitive import failure**

   The directory is `backend/Agent`, but production code imports `backend.agent`. This may work on a default macOS filesystem but will fail on case-sensitive Linux hosts such as Render. Rename the directory to lowercase or update every import consistently.

2. **DCF denominator and required-input safety**

   `run_dcf()` does not reject `WACC <= terminal growth`, zero shares, empty periods, missing base revenue, or zero enterprise value. These cases can produce division errors, negative terminal values, or invalid ratios.

3. **Global deep-plan state**

   `Deep_Plan` is a module-level global. Concurrent users can overwrite each other's depth mode. It should be stored only in `AgentState`.

### High

4. **Requested recursion limit is ignored**

   `_agent_config()` always sets `DEFAULT_RECURSION_LIMIT * 1000` and does not use the request's `recursion_limit`. The separate force-response helper reads this inflated value, weakening the intended guard.

5. **Documentation drift**

   `README.md`, `ARCHITECTURE.md`, `AGENTIC.md`, and `STATUS.md` describe different historical graph designs, missing files, lowercase paths, and metrics not implemented in the live ratio service.

6. **Test drift and limited coverage**

   Some tests target removed helper functions. Core financial calculations lack regression tests.

7. **Blocking work inside sync API routes**

   EDGAR, Yahoo, FRED, and Damodaran calls are synchronous. Standard FastAPI `def` routes use a thread pool, but long network work and Excel downloads can still reduce capacity.

8. **External HTTP robustness**

   FRED uses `requests.get()` without an explicit timeout or `raise_for_status()`. Yahoo and Damodaran handling is also thin. Retries, timeouts, and clearer provider-specific exceptions are needed.

### Medium

9. **Financial terminology**

   `debt_to_equity` and `debt_to_assets` use total liabilities, not interest-bearing debt. The labels can mislead users.

10. **Historical assumption quality**

    DCF assumptions use simple averages, constant growth, and constant margins. Outliers, negative denominators, acquisitions, cyclicality, and recent trend weighting are not handled.

11. **Missing cash in the equity bridge**

    The DCF subtracts debt but does not add excess cash. This can materially understate equity value.

12. **Long-term growth is effectively global**

    `SectorData.long_term_growth_rate` defaults to 2.5%; it is not actually industry-specific.

13. **In-memory agent checkpointing**

    LangGraph conversation state disappears on process restart and is not shared across multiple backend instances. Persisted chat text remains, but agent cache and internal context do not.

14. **Comparables integration**

    Comparables are agent-only, have no REST endpoint, and rely on broad SIC mapping and externally downloaded spreadsheets.

15. **Frontend state concentration**

    `App.jsx` handles routing, data loading, sessions, messaging, profile state, health checks, and streaming. This will become difficult to maintain as features grow.

16. **No automated CI shown**

    The repository does not include an obvious workflow that installs dependencies, runs tests, and builds both applications for every pull request.

## 18. Recommended Priorities

### Priority 1: Make Deployment Reliable

- Rename `Agent/` to `agent/` and normalize imports.
- Reinstall frontend dependencies from the lockfile.
- Confirm `uv sync --frozen` in a clean environment.
- Add a CI workflow for backend tests and frontend build.
- Add a production startup smoke test.

### Priority 2: Protect Financial Correctness

- Validate all required DCF inputs.
- Reject or explicitly handle `WACC <= g`.
- Add cash to the enterprise-to-equity bridge.
- Clarify interest-bearing debt versus total liabilities.
- Add unit tests for every formula and edge case.
- Add DCF sensitivity tables for WACC and terminal growth.

### Priority 3: Stabilize the Agent

- Move deep-plan selection into state.
- Honor the user-provided recursion limit.
- Persist LangGraph checkpoints in a durable shared store.
- Test concurrent users and multi-ticker cache merges.
- Align prompt data definitions with actual ratio outputs.

### Priority 4: Reduce Documentation and Code Drift

- Treat this report or a revised architecture document as the canonical reference.
- Archive obsolete scripts or clearly mark experimental ones.
- Update endpoint and tool catalogues.
- Remove stale imports and dead test assumptions.

### Priority 5: Improve Maintainability

- Split frontend state into routing, sessions, profile, and chat hooks.
- Introduce typed frontend API contracts.
- Add structured logging and request IDs.
- Add provider timeouts, retries, and monitoring.
- Add integration tests using mocked external providers.

## 19. Overall Assessment

The project has a strong product concept and a surprisingly complete implementation: it can ingest filings, calculate financial analytics, run valuations, coordinate an LLM agent, stream results, authenticate users, persist chats, and export reports.

It should currently be considered a late prototype or early beta rather than production-ready. The architecture is capable of supporting a production system, but financial edge-case handling, import portability, concurrency safety, tests, dependency reproducibility, and documentation consistency need attention before users should rely on it for repeatable valuation work.

