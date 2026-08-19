"""Graph composition: wires nodes and edges into the compiled agent.

Node logic lives in nodes/, routing decisions in edges/, and invocation
entrypoints (activate_agent, activate_agent_async) in runtime.py.
"""

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from .edges import route_after_judge, route_after_plan, route_after_react, route_after_router
from .nodes import (
    exec_calc_node,
    exec_research_node,
    insight_node,
    judge_node,
    plan_node,
    react_node,
    response_node,
    router,
    scrape_node,
)
from .state import AgentState


def initialize_agent():
    """Build and compile the state graph used by API and CLI entrypoints.

    Tool execution topology: plan/react dispatch scrape_node and exec_research
    in parallel (both exactly one hop), converging on exec_calc — so
    assumptions/calculation tools see this same cycle's scrape and research
    writes before react runs, and exec_calc fires exactly once per cycle.
    insight_node then interprets each of the batch's tool results in parallel
    before react schedules the next cycle.
    """

    #Setting the state class in the agent
    agent_builder = StateGraph(AgentState)

    #Creating the graph nodes
    agent_builder.add_node("router", router)
    agent_builder.add_node("plan_node", plan_node)
    agent_builder.add_node("exec_research", exec_research_node)
    agent_builder.add_node("exec_calc", exec_calc_node)
    agent_builder.add_node("scrape_node", scrape_node)
    agent_builder.add_node("insight_node", insight_node)
    agent_builder.add_node("react_node", react_node)
    agent_builder.add_node("response_node", response_node)
    agent_builder.add_node("judge_node", judge_node)

    #Creating the graph edges that connect the different nodes
    agent_builder.add_edge(START, "router")
    agent_builder.add_conditional_edges("router", route_after_router, {"plan_node": "plan_node", "end": END})
    agent_builder.add_conditional_edges("plan_node", route_after_plan,
        {"exec_research": "exec_research", "scrape_node": "scrape_node", "response_node": "response_node"},
    )
    #Both one-hop branches converge on exec_calc, which always runs once per cycle
    agent_builder.add_edge("exec_research", "exec_calc")
    agent_builder.add_edge("scrape_node", "exec_calc")
    #Every batch is interpreted per-result (parallel LLM calls) before react schedules
    agent_builder.add_edge("exec_calc", "insight_node")
    agent_builder.add_edge("insight_node", "react_node")
    agent_builder.add_conditional_edges(
        "react_node",
        route_after_react,
        {"exec_research": "exec_research", "scrape_node": "scrape_node", "response_node": "response_node"},
    )
    agent_builder.add_edge("response_node", "judge_node")
    agent_builder.add_conditional_edges(
        "judge_node",
        route_after_judge,
        {"end": END, "revise": "react_node"},
    )

    #Returning compiled graph agent with MemorySaver to remember previous messages of the same conversation
    return agent_builder.compile(checkpointer=MemorySaver())
