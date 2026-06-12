"""Shared LLM invocation paths with prompt caching on the stable prefix."""

import json
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage

from backend.core.llm import CHAT_MODEL

from .cache import empty_data_catalog
from .messages import latest_human_message_content, messages_for_llm
from .prompts import data_dictionary
from .state import AgentState
from .tools import tools

CHAT_MODEL_WITH_TOOLS = CHAT_MODEL.bind_tools(tools)


async def invoke_llm(state: AgentState, prompt: str, use_tools: bool = False, data_payload: dict | None = None) -> AIMessage:
    system_blocks = build_system_prompt(state, prompt, data_payload=data_payload)
    model = CHAT_MODEL_WITH_TOOLS if use_tools else CHAT_MODEL
    return await model.ainvoke([SystemMessage(content=system_blocks)] + messages_for_llm(state))


async def invoke_llm_structured(state: AgentState, prompt: str, schema: type) -> Any:
    system_blocks = build_system_prompt(state, prompt)
    model = CHAT_MODEL.with_structured_output(schema)
    return await model.ainvoke([SystemMessage(content=system_blocks)] + messages_for_llm(state))


def build_system_prompt(state: AgentState, node_prompt: str, data_payload: dict | None = None) -> list[dict]:
    """Return system prompt as content blocks with cache_control on the stable prefix.

    The stable block (app_context + data_dictionary + node_prompt) is identical
    across all iterations of the same node type, so Anthropic caches it and serves
    subsequent calls at ~10% of normal input-token cost. The volatile block
    (runtime context) always changes and is never marked for caching.
    """
    context = {
        "latest_user_message": latest_human_message_content(state),
        "current_year": state.get("current_year"),
        "available_tools": state["available_tools"],
        "cached_data_catalog": state.get("data_catalog", empty_data_catalog()),
        "forced_response_due_to_recursion": state.get("forced_response_due_to_recursion", False),
        "scrape_history": state.get("scrape_history", [])[-20:],
        "previous_depth": state.get("previous_depth"),
    }
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
