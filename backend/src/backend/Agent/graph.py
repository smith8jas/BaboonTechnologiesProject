import json
from io import BytesIO
from datetime import date
from pathlib import Path
from uuid import uuid4

from langchain.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from .prompts import app_context, plan_prompt, response_prompt, router_prompt
from .state import CHAT_MODEL, AgentState
from .tools import tools


DEFAULT_RECURSION_LIMIT = 12


def initialize_agent(save_graph=False):
    agent_builder = StateGraph(AgentState)

    agent_builder.add_node("router", router)
    agent_builder.add_node("plan_node", plan_node)
    agent_builder.add_node(
        "tools",
        ToolNode(tools, name="tools", handle_tool_errors=True),
    )
    agent_builder.add_node("response_node", response_node)

    agent_builder.add_edge(START, "router")
    agent_builder.add_conditional_edges(
        "router",
        _route_after_router,
        {
            "plan_node": "plan_node",
            "end": END,
        },
    )
    agent_builder.add_conditional_edges(
        "plan_node",
        tools_condition,
        {
            "tools": "tools",
            "__end__": "response_node",
        },
    )
    agent_builder.add_edge("tools", "plan_node")
    agent_builder.add_edge("response_node", END)

    agent = agent_builder.compile(checkpointer=MemorySaver())

     
    if save_graph:
        _save_graph_mermaid(agent, Path(__file__).with_name("agent_graph.mmd"))
    return agent


def activate_agent(
    user_input,
    agent,
    message_history=None,
    *,
    thread_id: str | None = None,
    recursion_limit: int = DEFAULT_RECURSION_LIMIT,
):
    previous_message_count = len(message_history or [])
    thread_id = thread_id or (
        f"message-history-{id(message_history)}"
        if message_history is not None
        else f"session-{uuid4()}"
    )
    config = {
        "recursion_limit": recursion_limit,
        "configurable": {"thread_id": thread_id},
    }

    result = agent.invoke(_initial_state(user_input), config=config)

    if message_history is not None:
        message_history[:] = result["messages"]

    for message in result["messages"][previous_message_count:]:
        message.pretty_print()

    return result["messages"][-1].content


def _initial_state(user_input):
    return {
        "messages": [HumanMessage(content=user_input)],
        "context": app_context,
        "current_year": date.today().year,
        "available_tools": _serialize_tools(),
    }


def router(state: AgentState):
    print("Router Agent Activated")
    try:
        router_message = _invoke_llm(state, router_prompt)
    except Exception as exc:
        return {
            "messages": [AIMessage(content=f"I could not route the request reliably: {exc}")],
            "router_route": "end",
        }

    route_text = (router_message.content or "").strip()
    if route_text == "plan_node":
        return {"router_route": "plan_node"}

    answer = route_text or "How can I help with company valuation or financial analysis?"
    return {
        "messages": [AIMessage(content=answer)],
        "router_route": "end",
    }


def plan_node(state: AgentState):
    print("Plan Agent Activated")
    try:
        plan_message = _invoke_tool_calling_llm(state, plan_prompt)
    except Exception as exc:
        plan_message = AIMessage(
            content=(
                "I could not create a valid tool plan. Please provide the "
                f"company or ticker and the specific analysis you want. ({exc})"
            )
        )

    _print_tool_calls("Execution Plan", plan_message)
    return {"messages": [plan_message]}


def response_node(state: AgentState):
    print("Response Agent Activated")
    try:
        response_message = _invoke_llm(state, response_prompt)
    except Exception as exc:
        response_message = AIMessage(
            content=f"I gathered data but could not complete analysis: {exc}"
        )

    return {"messages": [response_message]}


def _route_after_router(state: AgentState) -> str:
    return state.get("router_route", "end")


def _invoke_tool_calling_llm(
    state: AgentState,
    prompt: str,
) -> AIMessage:
    context = {
        "latest_user_message": _latest_human_message_content(state),
        "current_year": state.get("current_year"),
        "available_tools": state["available_tools"],
    }
    system_prompt = _system_prompt(prompt, context)
    return CHAT_MODEL.bind_tools(tools).invoke(
        [SystemMessage(content=system_prompt)] + state["messages"]
    )


def _invoke_llm(
    state: AgentState,
    prompt: str,
) -> AIMessage:
    context = {
        "latest_user_message": _latest_human_message_content(state),
        "current_year": state.get("current_year"),
        "available_tools": state["available_tools"],
    }
    system_prompt = _system_prompt(prompt, context)
    return CHAT_MODEL.invoke([SystemMessage(content=system_prompt)] + state["messages"])


def _system_prompt(prompt: str, context: dict) -> str:
    return f"""
    {prompt}

    Runtime context:
    {json.dumps(context, indent=2, default=str)}
    """


def _print_tool_calls(label: str, message: AIMessage) -> None:
    tool_calls = getattr(message, "tool_calls", None) or []
    if tool_calls:
        print(f"{label}:")
        print(json.dumps(tool_calls, indent=2, default=str))


def _save_graph_mermaid(agent, output_path: Path) -> None:
    mermaid_text = agent.get_graph(xray=True).draw_mermaid()
    output_path.write_text(mermaid_text)
    print(f"[save_graph] Guardado en: {output_path}")


def _serialize_tools():
    return [
        {
            "name": tool.name,
            "description": getattr(tool, "description", "") or "",
            "args": getattr(tool, "args", {}) or {},
            "metadata": (getattr(tool, "metadata", None) or {}).get("agent", {}),
        }
        for tool in tools
    ]


def _latest_human_message_content(state) -> str:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage):
            return message.content

    return ""
