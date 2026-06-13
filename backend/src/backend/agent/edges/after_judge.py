"""Routing after judge_node."""

from ..state import AgentState


def route_after_judge(state: AgentState) -> str:
    if state.get("judge_verdict") == "revise":
        return "revise"
    return "end"
