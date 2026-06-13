"""React node: evaluates tool results and decides whether more data is needed."""

import logging

from langchain_core.messages import AIMessage

from ..constants import DEFAULT_RECURSION_LIMIT, SCRAPE_TOOL_NAME
from ..llm import invoke_llm
from ..messages import log_tool_calls
from ..prompts import deep_react_prompt, react_prompt
from ..state import AgentState
from .depth import is_deep_plan

logger = logging.getLogger(__name__)


async def react_node(state: AgentState):
    """Evaluate tool results and decide whether more tools are needed or data is sufficient."""
    logger.info("React Node Activated")
    local_prompt = deep_react_prompt if is_deep_plan() else react_prompt
    react_count = state.get("react_iterations", 0)
    #print(f"[REACT] Iteration {react_count + 1} | {'deep_react_prompt' if is_deep_plan() else 'react_prompt'} active")

    if react_count >= DEFAULT_RECURSION_LIMIT - 2:
        return {
            "plan_status": "ready_to_respond",
            "forced_response_due_to_recursion": True,
        }

    next_count = react_count + 1

    try:
        react_message = await invoke_llm(state, local_prompt, use_tools=True)
    except Exception as exc:
        return {
            "messages": [AIMessage(content=f"I could not evaluate tool results: {exc}")],
            "plan_status": "ready_to_respond",
            "react_iterations": next_count,
        }

    log_tool_calls("React Decision", react_message)
    tool_calls = getattr(react_message, "tool_calls", None) or []

    if tool_calls:
        has_scrape = any(tc.get("name") == SCRAPE_TOOL_NAME for tc in tool_calls)
        has_non_scrape = any(tc.get("name") != SCRAPE_TOOL_NAME for tc in tool_calls)
        if has_scrape and has_non_scrape:
            #print("[REACT] → needs_scrape_and_tools")
            return {
                "messages": [react_message],
                "plan_status": "needs_scrape_and_tools",
                "react_iterations": next_count,
            }
        if has_scrape:
            #print("[REACT] → needs_scrape")
            return {
                "messages": [react_message],
                "plan_status": "needs_scrape",
                "react_iterations": next_count,
            }
        #print("[REACT] → needs_tools")
        return {
            "messages": [react_message],
            "plan_status": "needs_tools",
            "react_iterations": next_count,
        }

    #print("[REACT] → ready_to_respond")
    return {"plan_status": "ready_to_respond", "react_iterations": next_count}
