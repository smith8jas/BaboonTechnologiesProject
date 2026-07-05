"""Conditional edge out of the plan node."""

from langgraph.types import Send

from ..state import AgentState


def route_after_plan(state: AgentState):
    """Route to execution, scraping, or response based on the latest plan status.

    Non-scrape tool calls enter through exec_research (even calculation-only
    batches — exec_research no-ops and falls through to exec_calc). Both
    branches are one hop, so when dispatched in parallel they converge on
    exec_calc in the same superstep.
    """
    status = state.get("plan_status")

    #If plan node decided scrape and tools are necessary, run both branches in parallel
    if status == "needs_scrape_and_tools":
        return [Send("scrape_node", state), Send("exec_research", state)]
    #If it only needs one it calls the respective branch.
    if status == "needs_scrape":
        return "scrape_node"
    if status == "needs_tools":
        return "exec_research"
    #Else, calls response_node
    return "response_node"
