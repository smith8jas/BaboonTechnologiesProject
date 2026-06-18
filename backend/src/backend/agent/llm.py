"""Shared LLM invocation paths with prompt caching on the stable prefix."""

import json
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage

from backend.core.llm import NODE_PROVIDERS, get_node_model

from .messages import current_tool_block, last_human_from_dialogue
from .state import AgentState
from .tools import tools

# Message list each node receives. All message-routing policy lives here.
_NODE_MESSAGES: dict[str, str] = {
    "router":   "dialogue",
    "plan":     "dialogue",
    "react":    "last_human_and_tool_block",
    "response": "dialogue_and_tool_block",
    "judge":    "dialogue",
    "scrape":   "none",
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
    return []


# Fields each node receives in runtime_context beyond current_year (always included).
# All "who sees what" policy lives here — nodes just pass their name to invoke_llm*.
_NODE_CONTEXT: dict[str, set[str]] = {
    "router":   {"available_tools", "previous_depth"},
    "plan":     {"available_tools", "cached_data_catalog"},
    "react":    {"available_tools", "cached_data_catalog", "scrape_history", "judge_rationale"},
    "response": {"scrape_history", "forced_response_due_to_recursion"},
    "judge":    set(),
    "scrape":   {"scrape_history"},
}


async def invoke_llm(
    state: AgentState,
    prompt: str,
    node: str,
    use_tools: bool = False,
    data_payload: dict | None = None,
    messages: list | None = None,
) -> AIMessage:
    system_blocks = build_system_prompt(state, prompt, node, data_payload=data_payload)
    model = get_node_model(node)
    if use_tools:
        model = model.bind_tools(tools)
    msgs = messages if messages is not None else _resolve_messages(state, node)
    return await model.ainvoke([SystemMessage(content=system_blocks)] + msgs)


async def invoke_llm_structured(
    state: AgentState,
    prompt: str,
    schema: type,
    node: str,
    messages: list | None = None,
) -> Any:
    system_blocks = build_system_prompt(state, prompt, node)
    model = get_node_model(node).with_structured_output(schema, method="function_calling")
    msgs = messages if messages is not None else _resolve_messages(state, node)
    return await model.ainvoke([SystemMessage(content=system_blocks)] + msgs)


def build_system_prompt(
    state: AgentState,
    node_prompt: str,
    node: str,
    data_payload: dict | None = None,
) -> list[dict]:
    """Return system prompt as content blocks, with Anthropic cache_control on the stable block.

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
        f"    Node instructions:\n    {node_prompt}"
    )
    volatile = f"\n\n    Runtime context:\n    {json.dumps(context, indent=2, default=str)}\n    "

    stable_block: dict = {"type": "text", "text": stable}
    if NODE_PROVIDERS.get(node) == "anthropic":
        stable_block["cache_control"] = {"type": "ephemeral"}

    return [stable_block, {"type": "text", "text": volatile}]
