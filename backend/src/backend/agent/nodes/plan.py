"""Plan node: generates the initial tool-call batch and guidance for react."""

import logging

from langchain_core.messages import AIMessage

from ..constants import SCRAPE_TOOL_NAME
from ..llm import invoke_llm
from ..messages import log_tool_calls
from ..prompts import deep_plan_prompt, plan_prompt
from ..state import AgentState
from .depth import is_deep_plan

logger = logging.getLogger(__name__)


async def plan_node(state: AgentState):
    """Generate the initial tool call batch and write planning guidance for react_node."""
    logger.info("Plan Node Activated")
    local_prompt = deep_plan_prompt if is_deep_plan() else plan_prompt
    print(f"[PLAN] {'deep_plan_prompt' if is_deep_plan() else 'plan_prompt'} active")

    try:
        plan_message = await invoke_llm(state, local_prompt, use_tools=True)
    except Exception as exc:
        return {
            "messages": [AIMessage(content=f"I could not create a valid tool plan: {exc}")],
            "plan_status": "ready_to_respond",
            "plan_iterations": 1,
        }

    # Extract planning rationale text (written before tool calls) as tool_guidance
    content = plan_message.content
    if isinstance(content, str):
        guidance_text = content.strip()
    elif isinstance(content, list):
        text_parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        guidance_text = " ".join(text_parts).strip()
    else:
        guidance_text = ""

    log_tool_calls("Execution Plan", plan_message)
    tool_calls = getattr(plan_message, "tool_calls", None) or []

    if tool_calls:
        has_scrape = any(tc.get("name") == SCRAPE_TOOL_NAME for tc in tool_calls)
        has_non_scrape = any(tc.get("name") != SCRAPE_TOOL_NAME for tc in tool_calls)
        if has_scrape and has_non_scrape:
            return {
                "messages": [plan_message],
                "plan_status": "needs_scrape_and_tools",
                "plan_iterations": 1,
                "tool_guidance": guidance_text,
            }
        if has_scrape:
            return {
                "messages": [plan_message],
                "plan_status": "needs_scrape",
                "plan_iterations": 1,
                "tool_guidance": guidance_text,
            }
        return {
            "messages": [plan_message],
            "plan_status": "needs_tools",
            "plan_iterations": 1,
            "tool_guidance": guidance_text,
        }

    # No tool calls generated — fall through directly to response
    return {
        "plan_status": "ready_to_respond",
        "plan_iterations": 1,
        "tool_guidance": guidance_text,
    }
