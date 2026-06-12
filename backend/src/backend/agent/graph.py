"""Graph composition: wires nodes and edges into the compiled agent.

Node logic lives in nodes/, routing decisions in edges/, and invocation
entrypoints (activate_agent, activate_agent_async) in runtime.py.
"""

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from .edges import route_after_plan, route_after_react, route_after_router
from .nodes import plan_node, react_node, response_node, router, scrape_node, tools_node
from .state import AgentState


def initialize_agent():
    """Build and compile the state graph used by API and CLI entrypoints."""
    agent_builder = StateGraph(AgentState)

    agent_builder.add_node("router", router)
    agent_builder.add_node("plan_node", plan_node)
    agent_builder.add_node("tools", tools_node)
    agent_builder.add_node("scrape_node", scrape_node)
    agent_builder.add_node("react_node", react_node)
    agent_builder.add_node("response_node", response_node)

    agent_builder.add_edge(START, "router")
    agent_builder.add_conditional_edges("router", route_after_router, {"plan_node": "plan_node", "end": END})
    agent_builder.add_conditional_edges(
        "plan_node",
        route_after_plan,
        {"tools": "tools", "scrape_node": "scrape_node", "response_node": "response_node"},
    )
    agent_builder.add_edge("tools", "react_node")
    agent_builder.add_edge("scrape_node", "react_node")
    agent_builder.add_conditional_edges(
        "react_node",
        route_after_react,
        {"tools": "tools", "scrape_node": "scrape_node", "response_node": "response_node"},
    )
    agent_builder.add_edge("response_node", END)

    return agent_builder.compile(checkpointer=MemorySaver())
