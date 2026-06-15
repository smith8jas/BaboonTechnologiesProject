"""Conditional edge out of the plan node."""

from langgraph.types import Send

from ..state import AgentState


def route_after_plan(state: AgentState):
    """Route to tools, scraping, or response based on the latest plan status."""
    status = state.get("plan_status")

    #If plan node decided scrape and tools is necessary, it calls both scrape and tool nodes
    if status == "needs_scrape_and_tools":
        return [Send("scrape_node", state), Send("tools", state)]
    #If it only needs one it calls the respective node.
    if status == "needs_scrape":
        return "scrape_node"
    if status == "needs_tools":
        return "tools"
    #Else, calls response_node
    return "response_node"
