"""Plan node: generates the initial tool-call batch and guidance for react."""

import logging
import uuid
from enum import Enum
from typing import Any

from langchain_core.messages import AIMessage
from pydantic import BaseModel

from ..constants import SCRAPE_TOOL_NAME
from ..llm import invoke_llm_structured
from ..messages import log_tool_calls
from ..prompts import deep_plan_prompt, plan_prompt
from ..state import AgentState
from ..tools import TOOLS_BY_NAME

logger = logging.getLogger(__name__)

# Enum built from TOOLS_BY_NAME so tool names are a single source of truth.
# The JSON schema sent to the LLM lists valid values automatically.
ToolName = Enum("ToolName", {k: k for k in TOOLS_BY_NAME})


class ToolCallSpec(BaseModel):
    tool_name: ToolName
    # Args vary per tool; the model uses available_tools in runtime context for the schema.
    args: dict[str, Any] = {}


class PlanDecision(BaseModel):
    rationale: str
    tool_calls: list[ToolCallSpec] = []


async def plan_node(state: AgentState):
    """Generate the initial tool call batch and write planning guidance for react_node."""
    logger.info("Plan Node Activated")

    #Creates the system prompt
    local_prompt = deep_plan_prompt if state.get("deep_plan") else plan_prompt

    #Invokes llm to fill in PlanDecision
    try:
        decision: PlanDecision = await invoke_llm_structured(state, local_prompt, PlanDecision, node="plan")
    except Exception as exc:
        return {
            "messages": [AIMessage(content=f"I could not create a valid tool plan: {exc}")],
            "plan_status": "ready_to_respond",
        }

    # Builds a list of tool calls from PlanDecision in structured format with "name" and "args"
    lc_tool_calls = [
        {
            "id": str(uuid.uuid4()),
            "name": tc.tool_name.value, #Name of tool
            "args": tc.args, #Arguments to input in tool
            "type": "tool_call",
        }
        for tc in decision.tool_calls
    ]

    #Updates plan_message to include a decision rationale and the structured tool calls
    plan_message = AIMessage(content=decision.rationale, tool_calls=lc_tool_calls)
    log_tool_calls("Execution Plan", plan_message)

    #If tool calls are made
    if lc_tool_calls:
        #Identifies if a tool has scrape in it
        has_scrape = any(tc["name"] == SCRAPE_TOOL_NAME for tc in lc_tool_calls)
        #Identifies if a tool does not have scrape in it
        has_non_scrape = any(tc["name"] != SCRAPE_TOOL_NAME for tc in lc_tool_calls)
        
        #Returns a plan_status (used by the following conditional edge) to decide what tool nodes to call
        #The list of tool calls is in plan_message stored in messages
        if has_scrape and has_non_scrape:
            return {
                "messages": [plan_message],
                "plan_status": "needs_scrape_and_tools",
                "tool_guidance": decision.rationale,
            }
        if has_scrape:
            return {
                "messages": [plan_message],
                "plan_status": "needs_scrape",
                "tool_guidance": decision.rationale,
            }
        return {
            "messages": [plan_message],
            "plan_status": "needs_tools",
            "tool_guidance": decision.rationale,
        }

    # No tool calls — fall through directly to response
    return {
        "plan_status": "ready_to_respond",
        "tool_guidance": decision.rationale,
    }
