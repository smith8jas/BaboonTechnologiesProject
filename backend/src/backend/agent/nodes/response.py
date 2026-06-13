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
    
    #Builds prompt; append judge critique instruction after a judge pass
    local_prompt = deep_response_prompt if state.get("deep_plan") else response_prompt
    if state.get("judge_iterations", 0) > 0:
        local_prompt = local_prompt + judge_response_addendum

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

    #After a judge pass, surface its critique directly in gathered_data so the LLM
    #sees exactly what needs to be fixed when rewriting the response.
    if state.get("judge_iterations", 0) > 0 and (rationale := state.get("judge_rationale")):
        payload = {**payload, "judge_critique": rationale}

    #Invokes llm with system prompt and payload
    try:
        response_message = await invoke_llm(state, local_prompt, node="response", data_payload=payload)
    except Exception as exc:
        response_message = AIMessage(
            content=f"I gathered data but could not complete analysis: {exc}"
        )
    
    #Returns response
    return {"messages": [response_message]}
