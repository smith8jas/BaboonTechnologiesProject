"""Router node: decides whether to answer directly or enter the planning path."""

import logging
from typing import Literal

from langchain_core.messages import AIMessage
from pydantic import BaseModel

from ..cache.session import purge_old_data, set_session_cycle
from ..llm import invoke_llm_structured
from ..prompts import router_prompt
from ..state import AgentState

logger = logging.getLogger(__name__)


class RouterDecision(BaseModel):
    """Structured router output that decides whether the graph needs tools."""

    route: Literal["plan_node", "end"]
    Deep_Plan: bool = False
    answer: str | None = None


async def router(state: AgentState):
    """Decide whether to answer directly or enter the planning/tool path.
    It's purpose is to bounce questions out of scope outside of the process"""

    logger.info("Router Node Activated")

    query_count = state.get("query_count", 0) + 1
    session_id = state.get("session_id") or ""

    if session_id:
        set_session_cycle(session_id, query_count)
        if query_count % 5 == 0:
            purge_old_data(session_id, query_count)

    #Tries invoking the llm with the state, router_prompt and RouterDecision pydantic structure
    try:
        decision: RouterDecision = await invoke_llm_structured(state, router_prompt, RouterDecision, node="router")
    #If anything fails it sets routes the process to the end of the graph and prints ("I could not route the request reliably: "error details")
    except Exception as exc:
        return {
            "messages": [AIMessage(content=f"I could not route the request reliably: {exc}")],
            "router_route": "end",
            "deep_plan": False,
            "query_count": query_count,
        }
    
    #Prints Deep Plan if the router decided the Analysis needs a Deep Plan.

    #Sets the path to plan node if router chose it
    if decision.route == "plan_node":
        return {"router_route": "plan_node", "deep_plan": decision.Deep_Plan, "query_count": query_count}

    #Sets path to end if router dit not choose plan and either prints an llm response or a premade response.
    answer = decision.answer or "I can help with public-company valuation and financial analysis. What company or ticker would you like to analyze?"
    return {
        "messages": [AIMessage(content=answer)],
        "router_route": "end",
        "deep_plan": False,
        "query_count": query_count,
    }
