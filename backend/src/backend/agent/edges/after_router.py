"""Conditional edge out of the router node."""

from ..state import AgentState


def route_after_router(state: AgentState) -> str:
    """Route according to the structured router decision, defaulting to end."""
    return state.get("router_route", "end")
