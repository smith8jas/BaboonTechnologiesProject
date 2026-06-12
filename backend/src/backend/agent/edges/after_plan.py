"""Conditional edge out of the plan node."""

from langgraph.types import Send

from ..state import AgentState


def route_after_plan(state: AgentState):
    """Route to tools, scraping, or response based on the latest plan status."""
    status = state.get("plan_status")
    if status == "needs_scrape_and_tools":
        return [Send("scrape_node", state), Send("tools", state)]
    if status == "needs_scrape":
        return "scrape_node"
    if status == "needs_tools":
        return "tools"
    return "response_node"
