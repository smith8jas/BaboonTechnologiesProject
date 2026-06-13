"""Response node: composes the final user-facing answer from cached data."""

import logging

from langchain_core.messages import AIMessage

from ..cache import build_data_payload, state_cache
from ..llm import invoke_llm
from ..prompts import deep_response_prompt, response_prompt
from ..state import AgentState
from .depth import is_deep_plan

logger = logging.getLogger(__name__)


async def response_node(state: AgentState):
    """Generate the final user-facing answer from messages and cached data."""
    logger.info("Response Node Activated")
    #print("[RESPONSE] Generating final answer...")
    local_prompt = deep_response_prompt if is_deep_plan() else response_prompt
    payload = build_data_payload(state_cache(state))
    if guidance := state.get("tool_guidance"):
        payload = {**payload, "analysis_plan": guidance}
    try:
        response_message = await invoke_llm(state, local_prompt, data_payload=payload)
    except Exception as exc:
        response_message = AIMessage(
            content=f"I gathered data but could not complete analysis: {exc}"
        )

    return {"messages": [response_message]}
