"""Shared LLM invocation paths with prompt caching on the stable prefix."""

import json
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage

from backend.core.llm import CHAT_MODEL

from .messages import messages_for_llm
from .prompts import data_dictionary
from .state import AgentState
from .tools import tools

CHAT_MODEL_WITH_TOOLS = CHAT_MODEL.bind_tools(tools)

# Fields each node receives in runtime_context beyond current_year (always included).
# All "who sees what" policy lives here — nodes just pass their name to invoke_llm*.
_NODE_CONTEXT: dict[str, set[str]] = {
    "router":   {"available_tools", "previous_depth"},
    "plan":     {"available_tools"},
    "react":    {"available_tools", "cached_data_catalog", "scrape_history", "judge_rationale"},
    "response": {"cached_data_catalog", "scrape_history", "forced_response_due_to_recursion"},
    "judge":    set(),
}


async def invoke_llm(
    state: AgentState,
    prompt: str,
    node: str,
    use_tools: bool = False,
    data_payload: dict | None = None,
) -> AIMessage:
    system_blocks = build_system_prompt(state, prompt, node, data_payload=data_payload)
    model = CHAT_MODEL_WITH_TOOLS if use_tools else CHAT_MODEL
    return await model.ainvoke([SystemMessage(content=system_blocks)] + messages_for_llm(state))


async def invoke_llm_structured(
    state: AgentState,
    prompt: str,
    schema: type,
    node: str,
) -> Any:
    system_blocks = build_system_prompt(state, prompt, node)
    model = CHAT_MODEL.with_structured_output(schema, method="function_calling")
    return await model.ainvoke([SystemMessage(content=system_blocks)] + messages_for_llm(state))


def build_system_prompt(
    state: AgentState,
    node_prompt: str,
    node: str,
    data_payload: dict | None = None,
) -> list[dict]:
    """Return system prompt as content blocks with cache_control on the stable prefix.

    The stable block (app_context + data_dictionary + node_prompt) is identical
    across all iterations of the same node type, so Anthropic caches it and serves
    subsequent calls at ~10% of normal input-token cost. The volatile block
    (runtime context) always changes and is never marked for caching.

    node: key into _NODE_CONTEXT — all policy on who sees what lives there.
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
    # Sourced from deep_plan so the router reads the prior turn's depth decision
    # without needing a separate previous_depth state field.
    if "previous_depth" in include:
        context["previous_depth"] = state.get("deep_plan")
    if "judge_rationale" in include:
        if state.get("judge_iterations", 0) > 0 and state.get("judge_rationale"):
            context["judge_rationale"] = state["judge_rationale"]
    if data_payload is not None:
        context["gathered_data"] = data_payload

    stable = (
        f"\n    Universal agent instructions:\n    {state.get('context', '')}\n\n"
        f"    Data dictionary:\n    {data_dictionary}\n\n"
        f"    Node instructions:\n    {node_prompt}"
    )
    volatile = f"\n\n    Runtime context:\n    {json.dumps(context, indent=2, default=str)}\n    "

    return [
        {"type": "text", "text": stable, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": volatile},
    ]
