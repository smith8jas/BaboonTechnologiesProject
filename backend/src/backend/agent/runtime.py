"""Agent invocation entrypoints and per-turn configuration helpers."""

import asyncio
from datetime import date
from typing import Any

from langchain_core.messages import HumanMessage

from .constants import DEFAULT_RECURSION_LIMIT
from .prompts import app_context
from .tools import AVAILABLE_TOOLS


def activate_agent(
    user_input,
    agent,
    *,
    thread_id: str,
    recursion_limit: int = DEFAULT_RECURSION_LIMIT,
    debug_updates: bool = False,
):
    """Synchronous wrapper for callers that do not run an event loop."""
    return asyncio.run(
        activate_agent_async(
            user_input,
            agent,
            thread_id=thread_id,
            recursion_limit=recursion_limit,
            debug_updates=debug_updates,
        )
    )


async def activate_agent_async(
    user_input,
    agent,
    *,
    thread_id: str,
    recursion_limit: int = DEFAULT_RECURSION_LIMIT,
    debug_updates: bool = False,
):
    """Invoke the agent graph and return the final assistant message content."""
    config = agent_config(thread_id, recursion_limit)

    previous_state = await agent.aget_state(config)
    set_turn_start_step(config, previous_state)
    previous_messages = previous_state.values.get("messages", []) if previous_state else []
    previous_message_count = len(previous_messages)

    if debug_updates:
        async for update in agent.astream(initial_state(user_input), config=config, stream_mode="updates"):
            print(update)
        result = (await agent.aget_state(config)).values
    else:
        result = await agent.ainvoke(initial_state(user_input), config=config)

    return result["messages"][-1].content


def agent_config(thread_id: str, recursion_limit: int = DEFAULT_RECURSION_LIMIT):
    """Build the LangGraph config that carries thread and recursion metadata."""
    return {
        "recursion_limit": DEFAULT_RECURSION_LIMIT * 1000,
        "configurable": {"thread_id": thread_id},
    }


def set_turn_start_step(config: dict[str, Any], state_snapshot) -> None:
    """Remember the prior graph step so recursion limits are per user turn."""
    metadata = getattr(state_snapshot, "metadata", None) or {}
    turn_start_step = metadata.get("step", -1)
    config.setdefault("configurable", {})["turn_start_step"] = turn_start_step


def initial_state(user_input):
    return {
        "messages": [HumanMessage(content=user_input)],
        "context": app_context,
        "current_year": date.today().year,
        "available_tools": AVAILABLE_TOOLS,
        "forced_response_due_to_recursion": False,
    }


def should_force_response(config: dict[str, Any]) -> bool:
    """Return True when the current turn is close to its recursion budget."""
    current_step = (config.get("metadata") or {}).get("langgraph_step")
    if current_step is None:
        return False

    turn_start_step = (config.get("configurable") or {}).get("turn_start_step", -1)
    recursion_limit = int(config.get("recursion_limit") or DEFAULT_RECURSION_LIMIT)
    turn_step = int(current_step) - int(turn_start_step)
    return turn_step >= recursion_limit - 2
