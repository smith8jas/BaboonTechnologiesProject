import json
from io import BytesIO
from datetime import date
from pathlib import Path
from typing import Any, Literal

from langchain.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command
from pydantic import BaseModel, Field

from .graph_helpers import (
    FINANCIAL_STATEMENT_TOOLS,
    GROWTH_TOOLS,
    MARKET_DATA_TOOLS,
    RATIO_TOOLS,
    SECTOR_DATA_TOOLS,
    extend_tool_plan as _extend_tool_plan,
    fallback_react_answer as _fallback_react_answer,
    latest_human_message_content as _latest_human_message_content,
    messages_for_llm as _messages_for_llm,
    next_financial_dependent_route as _next_financial_dependent_route,
    next_route_from_tool_plan as _next_route_from_tool_plan,
    run_financial_dependent_tools as _run_financial_dependent_tools,
    run_planned_tools as _run_planned_tools,
    serialize_tool_groups as _serialize_tool_groups,
    serialize_tools as _serialize_tools,
    tool_results_for_prompt as _tool_results_for_prompt,
)
from .prompts import app_context, plan_prompt, react_prompt, router_prompt
from .state import CHAT_MODEL, AgentState


END_ROUTE = "end"
ROUTER_NODE = "router"
PLAN_NODE = "plan_node"
MARKET_DATA_NODE = "market_data_node"
SECTOR_DATA_NODE = "sector_data_node"
FINANCIALS_NODE = "financials_node"
GROWTH_RATES_NODE = "growth_rates_node"
RATIOS_NODE = "ratios_node"
REACT_NODE = "react_node"

ROUTE_ALIASES = {
    "plan": PLAN_NODE,
    "market_data": MARKET_DATA_NODE,
    "sector_data": SECTOR_DATA_NODE,
    "financials": FINANCIALS_NODE,
    "growth_rates": GROWTH_RATES_NODE,
    "ratios": RATIOS_NODE,
    REACT_NODE: REACT_NODE,
    END_ROUTE: END_ROUTE,
}
REACT_NODE_ROUTES = {
    MARKET_DATA_NODE,
    SECTOR_DATA_NODE,
    FINANCIALS_NODE,
    GROWTH_RATES_NODE,
    RATIOS_NODE,
    END_ROUTE,
}


class RouterDecision(BaseModel):
    route: Literal[PLAN_NODE, END_ROUTE]
    answer: str = ""


class ToolStep(BaseModel):
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class PlanDecision(BaseModel):
    route: Literal[MARKET_DATA_NODE, SECTOR_DATA_NODE, FINANCIALS_NODE, END_ROUTE]
    tool_plan: list[ToolStep] = Field(default_factory=list)
    answer: str = ""


class ReactDecision(BaseModel):
    route: Literal[
        MARKET_DATA_NODE,
        SECTOR_DATA_NODE,
        FINANCIALS_NODE,
        GROWTH_RATES_NODE,
        RATIOS_NODE,
        END_ROUTE,
    ]
    tool_plan: list[ToolStep] = Field(default_factory=list)
    answer: str = ""


def initialize_agent():
    # Build the LangGraph state machine and register each agent node.
    agent_builder = StateGraph(AgentState)

    for name, node in {
        ROUTER_NODE: router,
        PLAN_NODE: plan_node,
        MARKET_DATA_NODE: market_data_node,
        SECTOR_DATA_NODE: sector_data_node,
        FINANCIALS_NODE: financials_node,
        GROWTH_RATES_NODE: growth_rates_node,
        RATIOS_NODE: ratios_node,
        REACT_NODE: react_node,
    }.items():
        agent_builder.add_node(name, node)

    # Each node returns a Command with the next graph node selected by the LLM or plan.
    agent_builder.add_edge(START, ROUTER_NODE)

    agent = agent_builder.compile()
    _save_graph_pdf(agent, Path(__file__).with_name("agent_graph.pdf"))
    return agent


def activate_agent(user_input, agent, message_history=None):
    # Terminal entry point: create state, run the graph, and print only new messages.
    existing_messages = message_history or []
    previous_message_count = len(existing_messages)

    messages = agent.invoke(_initial_state(user_input, existing_messages))

    if message_history is not None:
        # Keep chat history clean because OpenAI rejects orphan ToolMessages.
        message_history[:] = [
            message for message in messages["messages"]
            if not isinstance(message, ToolMessage)
        ]

    for m in messages["messages"][previous_message_count:]:
        m.pretty_print()
    
    return messages["messages"][-1].content


def _initial_state(user_input, existing_messages):
    # Create the state object expected by every LangGraph node.
    return {
        "messages": [*existing_messages, HumanMessage(content=user_input)],
        "context": app_context,
        "current_year": date.today().year,
        "available_tools": _serialize_tools(),
        "tool_plan": [],
        "tool_results": {},
        "llm_calls": 0,
        "max_llm_calls": 5,
        "route": "",
    }

def router(state: AgentState):
    # Router decides whether the request needs tools or can be answered immediately.
    print("Router Agent Activated")
    try:
        decision = _invoke_structured_llm(state, router_prompt, RouterDecision)
    except Exception as exc:
        return Command(
            goto=END,
            update={
                "messages": [
                    AIMessage(content=f"I could not route the request reliably: {exc}")
                ],
                "route": END_ROUTE,
                "llm_calls": state.get("llm_calls", 0) + 1,
            },
        )

    if decision.route == END_ROUTE:
        return Command(
            goto=END,
            update={
                "messages": [
                    AIMessage(
                        content=decision.answer
                        or "How can I help with company valuation or financial analysis?"
                    )
                ],
                "route": END_ROUTE,
                "llm_calls": state.get("llm_calls", 0) + 1,
            },
        )

    return Command(
        goto=PLAN_NODE,
        update={
            "route": PLAN_NODE,
            "llm_calls": state.get("llm_calls", 0) + 1,
        },
    )


def plan_node(state: AgentState):
    # Planner turns the user request into a structured tool plan.
    print("Plan Agent Activated")
    try:
        plan = _invoke_structured_llm(state, plan_prompt, PlanDecision)
    except Exception as exc:
        return Command(
            goto=END,
            update={
                "messages": [
                    AIMessage(
                        content=(
                            "I could not create a valid tool plan. Please provide the "
                            f"company or ticker and the specific analysis you want. ({exc})"
                        )
                    )
                ],
                "route": END_ROUTE,
                "llm_calls": state.get("llm_calls", 0) + 1,
            },
        )

    tool_plan = _tool_plan_dicts(plan.tool_plan)
    # Print the plan in terminal so debugging can show what the LLM decided.
    print("Execution Plan:")
    print(plan.model_dump_json(indent=2))

    # The first planned tool determines which graph node starts execution if needed.
    route = _normalize_route(plan.route)
    # If the planner decides not to use tools, return its direct answer.
    if route == END_ROUTE:
        answer = plan.answer or (
            "I need a company or ticker and the specific financial analysis you want."
        )
        return Command(
            goto=END,
            update={
                "messages": [
                    AIMessage(content=answer)
                ],
                "tool_plan": tool_plan,
                "route": END_ROUTE,
                "llm_calls": state.get("llm_calls", 0) + 1,
            },
        )

    return Command(
        goto=route,
        update={
            "tool_plan": tool_plan,
            "route": route,
            "llm_calls": state.get("llm_calls", 0) + 1,
        },
    )


def market_data_node(state: AgentState):
    # Execute only planned market data tool calls.
    return _data_tool_node(state, "Market Data Agent Activated", MARKET_DATA_TOOLS)


def sector_data_node(state: AgentState):
    # Execute only planned sector data tool calls.
    return _data_tool_node(state, "Sector Data Agent Activated", SECTOR_DATA_TOOLS)


def financials_node(state: AgentState):
    # Execute financial statements first; ratio/growth tools depend on these results.
    print("Financials Agent Activated")
    tool_results, tool_messages = _run_planned_tools(state, FINANCIAL_STATEMENT_TOOLS)
    route = _normalize_route(_next_financial_dependent_route(state, tool_results))
    return Command(
        goto=route,
        update={
            "messages": tool_messages,
            "tool_results": tool_results,
            "route": route,
        },
    )


def growth_rates_node(state: AgentState):
    # Execute planned growth-rate tools using already gathered financials.
    return _dependent_tool_node(state, "Growth Rates Agent Activated", GROWTH_TOOLS)


def ratios_node(state: AgentState):
    # Execute planned ratio tools using already gathered financials.
    return _dependent_tool_node(state, "Ratios Agent Activated", RATIO_TOOLS)


def _data_tool_node(state: AgentState, label: str, tool_names: set[str]) -> dict:
    # Shared runner for tools that can execute directly from planner-provided args.
    print(label)
    tool_results, tool_messages = _run_planned_tools(state, tool_names)
    return Command(
        goto=REACT_NODE,
        update={
            "messages": tool_messages,
            "tool_results": tool_results,
            "route": REACT_NODE,
        },
    )


def _dependent_tool_node(state: AgentState, label: str, tool_names: set[str]) -> dict:
    # Shared runner for tools that need previous financials injected into their args.
    print(label)
    tool_results, tool_messages = _run_financial_dependent_tools(state, tool_names)
    return Command(
        goto=REACT_NODE,
        update={
            "messages": tool_messages,
            "tool_results": tool_results,
            "route": REACT_NODE,
        },
    )

#React node receives all tool results and decides what to answer or what more to gather. It can loop back to any data node or end with an answer.
def react_node(state: AgentState):
    # React waits until all currently planned tool work has completed.
    pending_route = _normalize_route(
        _next_route_from_tool_plan(state, state.get("tool_results", {}))
    )
    if pending_route != REACT_NODE:
        return Command(goto=pending_route, update={"route": pending_route})

    print("React Agent Activated")
    # Stop before exceeding the configured LLM call budget.
    if state.get("llm_calls", 0) >= state.get("max_llm_calls", 5):
        return Command(
            goto=END,
            update={
                "messages": [AIMessage(content=_fallback_react_answer(state))],
                "route": END_ROUTE,
            },
        )

    # On the last available call, force react to answer instead of planning more work.
    force_final_answer = state.get("llm_calls", 0) >= state.get("max_llm_calls", 5) - 1
    try:
        decision = _invoke_structured_llm(
            state,
            react_prompt,
            ReactDecision,
            extra_context={
                "remaining_llm_calls_after_this_node": (
                    state.get("max_llm_calls", 5) - state.get("llm_calls", 0) - 1
                ),
                "force_final_answer": force_final_answer,
                "current_tool_plan": state.get("tool_plan", []),
                "gathered_tool_results": _tool_results_for_prompt(
                    state.get("tool_results", {})
                ),
            },
        )
    except Exception as exc:
        return Command(
            goto=END,
            update={
                "messages": [
                    AIMessage(content=f"I gathered data but could not complete analysis: {exc}")
                ],
                "route": END_ROUTE,
                "llm_calls": state.get("llm_calls", 0) + 1,
            },
        )

    # React may request another node, but invalid routes are forced to final answer.
    requested_tool_plan = _tool_plan_dicts(decision.tool_plan)
    route = _normalize_route(decision.route)
    if force_final_answer or route not in REACT_NODE_ROUTES:
        route = END_ROUTE

    if route == END_ROUTE:
        return Command(
            goto=END,
            update={
                "messages": [
                    AIMessage(
                        content=decision.answer
                        or "I gathered the available data, but I could not produce a final analysis."
                    )
                ],
                "route": END_ROUTE,
                "llm_calls": state.get("llm_calls", 0) + 1,
            },
        )

    # Add newly requested work while preserving results from previous nodes.
    tool_plan = _extend_tool_plan(
        state.get("tool_plan", []),
        requested_tool_plan,
    )
    return Command(
        goto=route,
        update={
            "tool_plan": tool_plan,
            "route": route,
            "llm_calls": state.get("llm_calls", 0) + 1,
        },
    )


def _invoke_structured_llm(
    state: AgentState,
    prompt: str,
    schema: type[BaseModel],
    extra_context: dict | None = None,
):
    context = {
        "request_context": state["context"],
        "latest_user_message": _latest_human_message_content(state),
        "current_year": state.get("current_year"),
        "available_tools": state["available_tools"],
        "tool_groups": _serialize_tool_groups(),
        "route_options": _route_options(schema),
    }
    if extra_context:
        context.update(extra_context)

    system_prompt = f"""
    {prompt}

    Runtime context:
    {json.dumps(context, indent=2, default=str)}
    """
    return CHAT_MODEL.with_structured_output(schema, method="function_calling").invoke(
        [SystemMessage(content=system_prompt)] + _messages_for_llm(state["messages"])
    )


def _tool_plan_dicts(tool_plan: list[ToolStep]) -> list[dict[str, Any]]:
    return [step.model_dump() for step in tool_plan]


def _normalize_route(route: str) -> str:
    return ROUTE_ALIASES.get(route, route)


def _route_options(schema: type[BaseModel]) -> list[str]:
    if schema is RouterDecision:
        return [PLAN_NODE, END_ROUTE]
    if schema is PlanDecision:
        return [MARKET_DATA_NODE, SECTOR_DATA_NODE, FINANCIALS_NODE, END_ROUTE]
    if schema is ReactDecision:
        return sorted(REACT_NODE_ROUTES)

    return []


def _save_graph_pdf(agent, output_path: Path) -> None:
    import matplotlib.image as mpimg
    import matplotlib.pyplot as plt

    png = agent.get_graph(xray=True).draw_mermaid_png()
    image = mpimg.imread(BytesIO(png), format="png")
    fig, ax = plt.subplots(figsize=(11, 8.5))
    ax.imshow(image)
    ax.axis("off")
    fig.savefig(output_path, format="pdf", bbox_inches="tight")
    plt.close(fig)
