"""React node: evaluates tool results and decides whether more data is needed."""

import logging
import uuid

from langchain_core.messages import AIMessage
from pydantic import BaseModel

from ..constants import REACT_LIMIT, SCRAPE_TOOL_NAME
from ..llm import invoke_llm_structured
from ..messages import log_tool_calls
from ..prompts import deep_react_prompt, judge_react_addendum, react_prompt
from ..state import AgentState
from .plan import ToolCallSpec


logger = logging.getLogger(__name__)


class ReactDecision(BaseModel):
    rationale: str
    tool_calls: list[ToolCallSpec] = []


async def react_node(state: AgentState):
    """Evaluate tool results and decide whether more tools are needed or data is sufficient."""
    logger.info("React Node Activated")
    
    #Defines system prompt; append judge context after a judge pass so react sees the critique
    local_prompt = deep_react_prompt if state.get("deep_plan") else react_prompt
    if state.get("judge_iterations", 0) > 0:
        local_prompt = local_prompt + judge_react_addendum
    
    #Gets react counter from State Class
    react_count = state.get("react_iterations", 0)

    #effective limit is REACT_LIMIT plus whatever additional recursions judge node allows
    effective_react_limit = REACT_LIMIT + state.get("judge_react_extensions", 0)
    
    #stops process to avoid infinite loops (each loop is an llm call which costs money)
    if react_count >= effective_react_limit - 2:
        return {
            "plan_status": "ready_to_respond",
            "forced_response_due_to_recursion": True,
        }
    
    next_count = react_count + 1

    #Invokes llm with prompt to fill in ReactDecision
    try:
        decision: ReactDecision = await invoke_llm_structured(state, local_prompt, ReactDecision, node="react")
    except Exception as exc:
        return {
            "messages": [AIMessage(content=f"I could not evaluate tool results: {exc}")],
            "plan_status": "ready_to_respond",
            "react_iterations": next_count,
        }
    
    #Makes structured list of tool calls from react decision
    lc_tool_calls = [
        {
            "id": str(uuid.uuid4()),
            "name": tc.tool_name.value,
            "args": tc.args,
            "type": "tool_call",
        }
        for tc in decision.tool_calls
    ]
    react_message = AIMessage(content=decision.rationale, tool_calls=lc_tool_calls)
    log_tool_calls("React Decision", react_message)

    #Decides plan_status depending on decision which is used by contitional edge after react_node
    #to choose which tool nodes to route to
    if lc_tool_calls:
        has_scrape = any(tc["name"] == SCRAPE_TOOL_NAME for tc in lc_tool_calls)
        has_non_scrape = any(tc["name"] != SCRAPE_TOOL_NAME for tc in lc_tool_calls)
        if has_scrape and has_non_scrape:
            return {
                "messages": [react_message],
                "plan_status": "needs_scrape_and_tools",
                "react_iterations": next_count,
            }
        if has_scrape:
            return {
                "messages": [react_message],
                "plan_status": "needs_scrape",
                "react_iterations": next_count,
            }
        return {
            "messages": [react_message],
            "plan_status": "needs_tools",
            "react_iterations": next_count,
        }

    return {"plan_status": "ready_to_respond", "react_iterations": next_count}
