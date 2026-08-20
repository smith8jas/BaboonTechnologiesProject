# LLM Provider Compatibility

Which providers work with the agent, and what breaks when they don't.

## What the agent requires

Five of the six agent nodes drive **structured output** — the model must return a value matching
a Pydantic schema, requested through LangChain's `with_structured_output`:

| Node | Schema | Fails if unsupported |
|---|---|---|
| `router` | `RouterDecision` | Nothing is routed; every request dies at the entry gate |
| `plan` | `PlanDecision` | No tool plan is produced |
| `react` | `ReactDecision` | The agent cannot decide whether it has enough data |
| `judge` | `JudgeDecision` | Response evaluation fails |
| `scrape` | `ScrapeDecision` | Web research queries cannot be generated |
| `response` | — | Plain text completion; works on any chat model |

A provider without reliable structured output cannot run this agent, no matter how good the
model is at analysis. `response` is the only node that will work anywhere.

Note: `router`, `plan`, `react`, and `judge` request structured output with
`method="function_calling"` explicitly; `scrape` uses the provider's default method. A provider
can pass on one path and fail on the other.

## Compatibility

### Fully compatible — recommended

| Provider | Model | API key |
|---|---|---|
| `openai` | `gpt-4o-mini` | `OPENAI_API_KEY` |
| `anthropic` | `claude-sonnet-4-6` | `ANTHROPIC_API_KEY` |
| `xai` | `grok-3` | `XAI_API_KEY` |
| `bedrock` | `anthropic.claude-3-5-sonnet-20241022-v2:0` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION` |

### Compatible, with quirks

Use the model named here specifically — others from the same provider have been observed to fail.

| Provider | Model | API key |
|---|---|---|
| `cohere` | `command-r-plus-08-2024` | `COHERE_API_KEY` |
| `google_genai` | `gemini-2.0-flash` | `GOOGLE_API_KEY` |
| `google_vertexai` | `gemini-2.0-flash` | GCP application default credentials |
| `groq` | `llama-3.3-70b-versatile` | `GROQ_API_KEY` |
| `mistralai` | `mistral-large-latest` | `MISTRAL_API_KEY` |
| `fireworks` | `accounts/fireworks/models/llama-v3p3-70b-instruct` | `FIREWORKS_API_KEY` |
| `together` | `meta-llama/Llama-3-70b-chat-hf` | `TOGETHER_API_KEY` |

**Cohere** — must be `command-r-plus-08-2024` (v1 API). `command-a-03-2025` (v2) has unreliable
structured output and crashes during streaming on `billed_units=None`. Tool parameters must not
carry null defaults: use `int` / `float`, not `int | None`.

**Gemini** (both `google_genai` and `google_vertexai`) — requires strict Human/AI message
alternation. Multi-turn tool loops can fail when consecutive same-role messages appear.

**Fireworks / Together** — OpenAI-compatible APIs, so they generally work, but open-source model
quality varies. Structured output is unreliable on smaller models.

### Not compatible

| Provider | Reason |
|---|---|
| `huggingface` | No reliable structured output or tool calling — `router` and `plan` fail |
| `ollama` | Same; local models lack dependable schema adherence |

## Choosing a model per node

Each node picks its own provider and model. Defaults live in `backend/src/backend/core/llm.py`:

| Node | Default provider | Default model |
|---|---|---|
| `router` | `openai` | `gpt-4.1` |
| `plan` | `openai` | `gpt-4.1` |
| `react` | `openai` | `gpt-4.1` |
| `response` | `anthropic` | `claude-sonnet-4-6` |
| `judge` | `openai` | `gpt-4.1` |
| `scrape` | `openai` | `gpt-5.4-mini` |

Override either half with environment variables, using the node name in uppercase:

```env
RESPONSE_LLM_PROVIDER=anthropic
RESPONSE_LLM_MODEL=claude-sonnet-4-6

SCRAPE_LLM_PROVIDER=groq
SCRAPE_LLM_MODEL=llama-3.3-70b-versatile
```

Set only the keys for providers you actually use. Models are constructed when
`core/llm.py` is imported, so an unrecognized provider string fails at startup rather than
mid-request.

`LLM_MAX_TOKENS` caps output length for every node when set.

## Where quality matters most

If you are mixing providers to control cost, spend the budget here first:

1. **`response`** — writes the final analysis. Model quality is most visible here.
2. **`judge`** — a weak judge produces bad critiques, which trigger revision loops that cost more
   than the model saved.
3. **`router`** — a false "deep analysis" classification makes the entire graph slower and more
   expensive for a question that did not need it.

`scrape` is the safest place to use a cheap, fast model.

## Caveat

This table records behavior observed during development, not results from an automated
compatibility suite. There is no CI job verifying any provider, and the code has no retry or
fallback when structured output fails — the node returns an error into agent state and the turn
degrades. Verify structured output and long-prompt instruction adherence yourself before trusting
an untested provider in a configuration you care about.

The prompts in `agent/prompts.py` run to hundreds of lines. Smaller models tend to follow the
opening sections and lose later instructions, including the loop-prevention rules.
