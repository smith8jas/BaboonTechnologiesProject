"""Shared LLM invocation paths with prompt caching on the stable prefix.

Cross-provider compatibility lives here: system prompt format (content blocks
vs plain string), structured-output method fallbacks, response content
normalization, and role-alternation quirks are all resolved in this module so
nodes stay provider-agnostic.
"""

import json
import logging
import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import ValidationError

from backend.core.llm import (
    NODE_PROVIDERS,
    STRICT_ROLE_PROVIDERS,
    SYSTEM_BLOCK_PROVIDERS,
    get_node_model,
    message_text,
    structured_method_ladder,
)

from .messages import current_tool_block, last_human_from_dialogue
from .state import AgentState
from .tools import tools

logger = logging.getLogger(__name__)

# Message list each node receives. All message-routing policy lives here.
_NODE_MESSAGES: dict[str, str] = {
    "router":   "dialogue",
    "plan":     "dialogue",
    "react":    "last_human_and_tool_block",
    "response": "dialogue",
    "judge":    "last_human",
    "scrape":   "none",
    "insight":  "none",
}


def _resolve_messages(state, node: str) -> list:
    strategy = _NODE_MESSAGES.get(node, "dialogue")
    if strategy == "dialogue":
        return list(state.get("dialogue", []))
    if strategy == "dialogue_and_tool_block":
        return list(state.get("dialogue", [])) + current_tool_block(state)
    if strategy == "last_human_and_tool_block":
        human = last_human_from_dialogue(state)
        block = current_tool_block(state)
        return ([human] if human else []) + block
    if strategy == "last_human":
        human = last_human_from_dialogue(state)
        return [human] if human else []
    return []


# Fields each node receives in runtime_context beyond current_year (always included).
# All "who sees what" policy lives here — nodes just pass their name to invoke_llm*.
_NODE_CONTEXT: dict[str, set[str]] = {
    "router":   {"available_tools", "previous_depth"},
    "plan":     {"available_tools", "cached_data_catalog"},
    "react":    {"available_tools", "cached_data_catalog", "scrape_history", "judge_rationale", "plan_rationale"},
    "response": {"scrape_history_current_query", "forced_response_due_to_recursion", "tool_insights"},
    "judge":    {"cached_data_catalog"},
    "scrape":   {"scrape_history"},
    # insight receives everything per-call via extra_context (one tool result each).
    "insight":  set(),
}

# HTTP statuses that no alternate structured-output method can fix — auth,
# permissions, rate limits. Re-raise immediately instead of burning calls.
_FATAL_STATUS_CODES = {401, 403, 429}


async def invoke_llm(
    state: AgentState,
    prompt: str,
    node: str,
    use_tools: bool = False,
    data_payload: dict | None = None,
    messages: list | None = None,
) -> AIMessage:
    system_content = build_system_prompt(state, prompt, node, data_payload=data_payload)
    model = get_node_model(node)
    if use_tools:
        model = model.bind_tools(tools)
    provider = NODE_PROVIDERS.get(node, "")
    msgs = _prepare_messages(
        messages if messages is not None else _resolve_messages(state, node), provider
    )
    return await model.ainvoke([SystemMessage(content=system_content)] + msgs)


async def invoke_llm_structured(
    state: AgentState,
    prompt: str,
    schema: type,
    node: str,
    messages: list | None = None,
    extra_context: dict | None = None,
) -> Any:
    """Invoke the node's model constrained to `schema`, degrading gracefully.

    Walks the provider's method ladder (see core.llm.STRUCTURED_METHOD_LADDERS):
    native methods first, then the universal "prompt_json" rung — a plain
    completion instructed to emit schema-conforming JSON, parsed and validated
    with one self-correcting retry. This keeps every provider usable, including
    those without native structured output (Ollama, HuggingFace).
    """
    system_content = build_system_prompt(state, prompt, node, extra_context=extra_context)
    provider = NODE_PROVIDERS.get(node, "")
    base_model = get_node_model(node)
    msgs = _prepare_messages(
        messages if messages is not None else _resolve_messages(state, node), provider
    )

    last_exc: Exception | None = None
    for method in structured_method_ladder(provider):
        if method == "prompt_json":
            return await _invoke_prompt_json(base_model, system_content, msgs, schema)
        try:
            model = base_model.with_structured_output(schema, method=method)
            result = await model.ainvoke([SystemMessage(content=system_content)] + msgs)
            if result is None:
                raise ValueError(f"structured output via {method} returned None")
            return result
        except Exception as exc:
            if _is_fatal(exc):
                raise
            logger.warning(
                "Structured output method %r failed for node=%s provider=%s (%s); "
                "falling back to next method",
                method, node, provider, exc,
            )
            last_exc = exc

    # Every ladder ends in prompt_json, so this is only reachable with a
    # misconfigured custom ladder.
    raise last_exc if last_exc else RuntimeError(f"empty structured-output ladder for {provider}")


def build_system_prompt(
    state: AgentState,
    node_prompt: str,
    node: str,
    data_payload: dict | None = None,
    extra_context: dict | None = None,
) -> list[dict] | str:
    """Return the system prompt in the node provider's native format.

    Anthropic-style providers get content blocks with cache_control on the
    stable block; everyone else gets a plain string (block lists are not
    portable across providers).

    node: key into _NODE_CONTEXT — all policy on who sees what lives there.
    extra_context: node-specific runtime fields merged into the volatile block
    (e.g. scrape's per-topic context).
    """
    include = _NODE_CONTEXT.get(node, set())

    # current_year is always included — every node needs temporal grounding.
    context: dict[str, Any] = {"current_year": state.get("current_year")}

    if "available_tools" in include:
        context["available_tools"] = state["available_tools"]
    if "cached_data_catalog" in include:
        context["cached_data_catalog"] = state.get("data_catalog") or {"companies": [], "global": {"sector_data_years": []}}
    if "forced_response_due_to_recursion" in include:
        context["forced_response_due_to_recursion"] = state.get("forced_response_due_to_recursion", False)
    if "scrape_history" in include:
        context["scrape_history"] = state.get("scrape_history", [])[-20:]
    # Same context key, narrower slice: react/scrape need cross-turn history for
    # dedup, but response only needs what was scraped for the current user query.
    if "scrape_history_current_query" in include:
        current_query = state.get("query_count", 0)
        history = [s for s in state.get("scrape_history", []) if s.get("query_index") == current_query]
        context["scrape_history"] = history[-20:]
    if "tool_insights" in include:
        # tool_insights accumulates across the whole conversation (operator.add);
        # only the entries written for the current user query are relevant context.
        if insights := state.get("tool_insights"):
            current_query = state.get("query_count", 0)
            if current := [i for i in insights if i.get("query_index") == current_query]:
                context["tool_insights"] = current
    # Sourced from tool_guidance so react keeps the current plan's rationale in
    # every cycle — the plan message itself leaves react's view after cycle 1.
    if "plan_rationale" in include:
        if guidance := state.get("tool_guidance"):
            context["plan_rationale"] = guidance
    # Sourced from deep_plan so the router reads the prior turn's depth decision
    # without needing a separate previous_depth state field.
    if "previous_depth" in include:
        context["previous_depth"] = state.get("deep_plan")
    if "judge_rationale" in include:
        if state.get("judge_iterations", 0) > 0 and state.get("judge_rationale"):
            context["judge_rationale"] = state["judge_rationale"]
    if extra_context:
        context.update(extra_context)
    if data_payload is not None:
        context["gathered_data"] = data_payload

    stable = (
        f"\n    Universal agent instructions:\n    {state.get('context', '')}\n\n"
        f"    Node instructions:\n    {node_prompt}"
    )
    volatile = f"\n\n    Runtime context:\n    {json.dumps(context, indent=2, default=str)}\n    "

    if NODE_PROVIDERS.get(node) in SYSTEM_BLOCK_PROVIDERS:
        stable_block = {"type": "text", "text": stable, "cache_control": {"type": "ephemeral"}}
        return [stable_block, {"type": "text", "text": volatile}]
    return stable + volatile


# ── Provider compatibility helpers ──────────────────────────────────────────

def _prepare_messages(msgs: list, provider: str) -> list:
    """Adapt the message list to the provider's conversation rules."""
    if not msgs:
        # Some providers (Gemini) reject system-only conversations.
        return [HumanMessage(content="Proceed according to the system instructions.")]
    if provider in STRICT_ROLE_PROVIDERS:
        return _merge_consecutive_humans(msgs)
    return msgs


def _merge_consecutive_humans(msgs: list) -> list:
    """Collapse consecutive HumanMessages for strict-alternation providers."""
    merged: list = []
    for m in msgs:
        if merged and isinstance(m, HumanMessage) and isinstance(merged[-1], HumanMessage):
            merged[-1] = HumanMessage(content=message_text(merged[-1]) + "\n\n" + message_text(m))
        else:
            merged.append(m)
    return merged


def _is_fatal(exc: Exception) -> bool:
    """True for failures no alternate structured-output method can fix."""
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    return status in _FATAL_STATUS_CODES


def _append_system_text(system_content: list[dict] | str, text: str) -> list[dict] | str:
    if isinstance(system_content, str):
        return system_content + text
    return system_content + [{"type": "text", "text": text}]


async def _invoke_prompt_json(model, system_content, msgs: list, schema: type) -> Any:
    """Universal structured-output fallback: instruct, parse, validate, retry once.

    The retry feeds the validation error back so the model can self-correct —
    this is what makes small/open models without native structured output
    produce usable decisions.
    """
    schema_json = json.dumps(schema.model_json_schema(), indent=2, default=str)
    instruction = (
        "\n\n    Output format (mandatory): respond with a single JSON object that"
        " validates against this JSON Schema. No prose, no markdown fences, no"
        f" explanations — only the JSON object.\n{schema_json}"
    )
    system = SystemMessage(content=_append_system_text(system_content, instruction))

    attempt_msgs = list(msgs)
    last_error: Exception | None = None
    for _ in range(2):
        response = await model.ainvoke([system] + attempt_msgs)
        text = message_text(response)
        try:
            return schema.model_validate(_extract_json(text))
        except (ValidationError, ValueError) as exc:
            last_error = exc
            attempt_msgs = attempt_msgs + [
                AIMessage(content=text),
                HumanMessage(
                    content=(
                        f"That response was not valid: {exc}. "
                        "Reply again with ONLY a corrected JSON object matching the schema."
                    )
                ),
            ]

    raise ValueError(f"prompt_json structured output failed after retry: {last_error}")


def _extract_json(text: str) -> Any:
    """Pull a JSON object out of a completion, tolerating fences and prose."""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t.strip())
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        start, end = t.find("{"), t.rfind("}")
        if start != -1 and end > start:
            return json.loads(t[start : end + 1])
        raise ValueError(f"no JSON object found in response: {text[:200]!r}")
