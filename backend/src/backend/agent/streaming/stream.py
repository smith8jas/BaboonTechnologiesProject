"""Streaming interfaces for the LangGraph agent."""

import asyncio
import logging

from ..constants import DEFAULT_RECURSION_LIMIT
from ..runtime import agent_config, initial_state, set_turn_start_step
from .events import events_from_node_update

logger = logging.getLogger(__name__)


def activate_agent_stream(
    user_input,
    agent,
    *,
    thread_id: str,
    recursion_limit: int = DEFAULT_RECURSION_LIMIT,
):
    """Synchronous generator wrapper around the async streaming interface."""
    chunks = asyncio.run(
        _collect_agent_stream(
            user_input,
            agent,
            thread_id=thread_id,
            recursion_limit=recursion_limit,
        )
    )
    yield from chunks


async def _collect_agent_stream(
    user_input,
    agent,
    *,
    thread_id: str,
    recursion_limit: int = DEFAULT_RECURSION_LIMIT,
) -> list[str]:
    """Collect streamed chunks into a list for the synchronous wrapper."""
    chunks = []
    async for chunk in activate_agent_stream_async(
        user_input,
        agent,
        thread_id=thread_id,
        recursion_limit=recursion_limit,
    ):
        chunks.append(chunk)
    return chunks


async def activate_agent_stream_async(
    user_input,
    agent,
    *,
    thread_id: str,
    recursion_limit: int = DEFAULT_RECURSION_LIMIT,
):
    """Stream the final assistant response from the agent graph asynchronously."""
    config = agent_config(thread_id, recursion_limit)
    previous_state = await agent.aget_state(config)
    set_turn_start_step(config, previous_state)
    emitted_response_tokens = False

    async for token, metadata in agent.astream(initial_state(user_input), config=config, stream_mode="messages"):
        if metadata.get("langgraph_node") != "response_node":
            continue

        content = getattr(token, "content", "")
        if not content:
            continue

        emitted_response_tokens = True
        yield content

    if emitted_response_tokens:
        return

    result = (await agent.aget_state(config)).values
    final_message = result.get("dialogue", [])[-1] if result.get("dialogue") else None
    fallback = getattr(final_message, "content", "")
    if fallback:
        yield fallback


async def activate_agent_stream_events_async(
    user_input,
    agent,
    *,
    thread_id: str,
    recursion_limit: int = DEFAULT_RECURSION_LIMIT,
):
    """Yield structured progress events plus token-by-token response deltas.

    Event shapes:
      {"type": "thought", "content": "<human-readable step description>"}
      {"type": "status",  "text":    "<short progress label>"}
      {"type": "delta",   "content": "<response text>"}
    """
    config = agent_config(thread_id, recursion_limit)
    previous_state = await agent.aget_state(config)
    set_turn_start_step(config, previous_state)
    emitted_response_tokens = False
    emitted_delta = False
    emitted_status_texts: set[str] = set()

    async for mode, data in agent.astream(
        initial_state(user_input),
        config=config,
        stream_mode=["updates", "messages"],
    ):
        if mode == "updates":
            for node_name, state_update in data.items():
                for event in events_from_node_update(node_name, state_update):
                    if event["type"] == "status":
                        text = event.get("text", "")
                        if text in emitted_status_texts:
                            continue
                        emitted_status_texts.add(text)
                    if event["type"] == "delta":
                        emitted_delta = True
                    yield event
            continue

        token, metadata = data
        if metadata.get("langgraph_node") != "response_node":
            continue

        content = getattr(token, "content", "")
        if not content:
            continue

        if not emitted_response_tokens:
            yield {"type": "status", "text": "Almost ready..."}
            emitted_response_tokens = True

        emitted_delta = True
        yield {"type": "delta", "content": content}

    if emitted_delta:
        return

    result = (await agent.aget_state(config)).values
    final_message = result.get("dialogue", [])[-1] if result.get("dialogue") else None
    fallback = getattr(final_message, "content", "")
    if fallback:
        yield {"type": "delta", "content": fallback}
