"""Response node: composes the final user-facing answer from research/calculated messages."""

import logging
from typing import Any

from langchain_core.messages import AIMessage

from ..llm import invoke_llm
from ..prompts import deep_response_prompt, judge_response_addendum, response_prompt
from ..state import AgentState

logger = logging.getLogger(__name__)


def _project(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop bookkeeping fields (tool, cycle, last_updated) the LLM doesn't need."""
    return [{"ticker": e["ticker"], "identifier": e["identifier"], "data": e["data"]} for e in entries]


async def response_node(state: AgentState):
    """Generate the final user-facing answer from messages and gathered data."""
    logger.info("Response Node Activated")

    #Builds prompt; append judge critique instruction and prior response after a judge revision
    local_prompt = deep_response_prompt if state.get("deep_plan") else response_prompt
    if state.get("judge_verdict") == "revise":
        local_prompt = local_prompt + judge_response_addendum
        if cr := state.get("current_response"):
            local_prompt += f"\n\nYour previous response that must be completely rewritten:\n{cr}"

    #Reads every research/calculated entry currently known this conversation — full
    #content, not windowed to the latest tool-calling round, and not summarized.
    payload = {
        "research": _project(state.get("research_messages", [])),
        "calculated": _project(state.get("calculated_messages", [])),
    }

    #Gets access to plan node's rationale for tool selection and appends it to payload
    if guidance := state.get("tool_guidance"):
        payload = {**payload, "analysis_plan": guidance}

    #After a judge revision, surface its critique directly in gathered_data.
    if state.get("judge_verdict") == "revise" and (rationale := state.get("judge_rationale")):
        payload = {**payload, "judge_critique": rationale}

    #Invokes llm with system prompt and payload
    try:
        response_message = await invoke_llm(state, local_prompt, node="response", data_payload=payload)
    except Exception as exc:
        response_message = AIMessage(
            content=f"I gathered data but could not complete analysis: {exc}"
        )
    
    #Returns response and stores it as current_response for judge/react to reference
    content = response_message.content
    if isinstance(content, list):
        content = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    result = {}
    if content:
        result["current_response"] = content
    return result
