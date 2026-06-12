"""Router node: decides whether to answer directly or enter the planning path."""

import logging
from typing import Literal

from langchain_core.messages import AIMessage
from pydantic import BaseModel

from ..llm import invoke_llm_structured
from ..prompts import router_prompt
from ..state import AgentState
from .depth import set_deep_plan

logger = logging.getLogger(__name__)


class RouterDecision(BaseModel):
    """Structured router output that decides whether the graph needs tools."""

    route: Literal["plan_node", "end"]
    Deep_Plan: bool = False
    answer: str | None = None


async def router(state: AgentState):
    """Decide whether to answer directly or enter the planning/tool path."""
    logger.info("Router Node Activated")
    try:
        decision: RouterDecision = await invoke_llm_structured(state, router_prompt, RouterDecision)
    except Exception as exc:
        set_deep_plan(False)
        return {
            "messages": [AIMessage(content=f"I could not route the request reliably: {exc}")],
            "router_route": "end",
        }

    print(f"[ROUTER] → {decision.route}{' (Deep Plan)' if decision.Deep_Plan else ''}")

    if decision.route == "plan_node":
        set_deep_plan(decision.Deep_Plan)
        return {"router_route": "plan_node", "plan_iterations": 0, "previous_depth": decision.Deep_Plan}

    set_deep_plan(False)
    answer = decision.answer or "I can help with public-company valuation and financial analysis. What company or ticker would you like to analyze?"
    return {
        "messages": [AIMessage(content=answer)],
        "router_route": "end",
    }
