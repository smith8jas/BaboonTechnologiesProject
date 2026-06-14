"""Response node: composes the final user-facing answer from cached data."""

import logging

from langchain_core.messages import AIMessage

from ..cache import build_data_payload
from ..cache.session import open_connection
from ..llm import invoke_llm
from ..prompts import deep_response_prompt, judge_response_addendum, response_prompt
from ..state import AgentState

logger = logging.getLogger(__name__)


async def response_node(state: AgentState):
    """Generate the final user-facing answer from messages and cached data."""
    logger.info("Response Node Activated")
    
    #Builds prompt; append judge critique instruction and prior response after a judge revision
    local_prompt = deep_response_prompt if state.get("deep_plan") else response_prompt
    if state.get("judge_verdict") == "revise":
        local_prompt = local_prompt + judge_response_addendum
        if cr := state.get("current_response"):
            local_prompt += f"\n\nYour previous response that must be completely rewritten:\n{cr}"

    #Opens connection to DuckDB with session_id stored in State Class
    session_id = state.get("session_id") or ""
    conn = open_connection(session_id)

    #Gets necessary data from DB for response node to read
    try:
        payload = build_data_payload(conn)
    finally:
        conn.close()

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
    result = {"messages": [response_message]}
    if content:
        result["current_response"] = content
    return result
