"""Conditional edge out of the react node."""

from langgraph.types import Send

from ..state import AgentState


def route_after_react(state: AgentState):
    """Route to execution, scraping, or response based on the react evaluation.

    Same topology as route_after_plan: one-hop branches converging on exec_calc.
    """
    status = state.get("plan_status")
    if status == "needs_scrape_and_tools":
        return [Send("scrape_node", state), Send("exec_research", state)]
    if status == "needs_scrape":
        return "scrape_node"
    if status == "needs_tools":
        return "exec_research"
    return "response_node"
