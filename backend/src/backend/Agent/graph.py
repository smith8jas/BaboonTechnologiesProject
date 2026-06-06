import json
from datetime import date

from langchain.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from .prompts import (
    app_context,
    plan_prompt,
    response_prompt,
    router_prompt,
)
from .state import CHAT_MODEL, AgentState
from .tools import tools


DEFAULT_RECURSION_LIMIT = 12

#Builds the node graph for the agent and returns the initialized agent
def initialize_agent():
    agent_builder = StateGraph(AgentState)

    agent_builder.add_node("router", RunnableLambda(router, arouter, name="router"))
    agent_builder.add_node("plan_node", RunnableLambda(plan_node, aplan_node, name="plan_node"))
    agent_builder.add_node("tools", ToolNode(tools, name="tools", handle_tool_errors=True),)
    agent_builder.add_node("response_node", RunnableLambda(response_node, aresponse_node, name="response_node"))

    agent_builder.add_edge(START, "router")
    agent_builder.add_conditional_edges("router",_route_after_router,{"plan_node": "plan_node","end": END,},)
    agent_builder.add_conditional_edges("plan_node",_route_after_plan,{"tools": "tools","response_node": "response_node",},)
    agent_builder.add_edge("tools", "plan_node")
    agent_builder.add_edge("response_node", END)

    agent = agent_builder.compile(checkpointer=MemorySaver())

    return(agent)

#Receives the user's input, an agent and some additional context. Invokes the agent with all the received info
def activate_agent(user_input, agent, *, thread_id: str, recursion_limit: int = DEFAULT_RECURSION_LIMIT, debug_updates: bool = False,):
    config = _agent_config(thread_id, recursion_limit)

    previous_state = agent.get_state(config)
    previous_messages = previous_state.values.get("messages", []) if previous_state else []
    previous_message_count = len(previous_messages)

    if debug_updates:
        for update in agent.stream(_initial_state(user_input), config=config, stream_mode="updates"):
            print(update)
        result = agent.get_state(config).values
    else:
        result = agent.invoke(_initial_state(user_input), config=config)

    for message in result["messages"][previous_message_count:]:
        message.pretty_print()

    return result["messages"][-1].content


async def activate_agent_async(user_input, agent, *, thread_id: str, recursion_limit: int = DEFAULT_RECURSION_LIMIT, debug_updates: bool = False,):
    config = _agent_config(thread_id, recursion_limit)

    previous_state = await agent.aget_state(config)
    previous_messages = previous_state.values.get("messages", []) if previous_state else []
    previous_message_count = len(previous_messages)

    if debug_updates:
        async for update in agent.astream(_initial_state(user_input), config=config, stream_mode="updates"):
            print(update)
        result = (await agent.aget_state(config)).values
    else:
        result = await agent.ainvoke(_initial_state(user_input), config=config)

    for message in result["messages"][previous_message_count:]:
        message.pretty_print()

    return result["messages"][-1].content


def activate_agent_stream(user_input, agent, *, thread_id: str, recursion_limit: int = DEFAULT_RECURSION_LIMIT):
    """Stream the final assistant response from the agent graph."""
    config = _agent_config(thread_id, recursion_limit)
    emitted_response_tokens = False

    for token, metadata in agent.stream(_initial_state(user_input), config=config, stream_mode="messages"):
        if metadata.get("langgraph_node") != "response_node":
            continue

        content = getattr(token, "content", "")
        if not content:
            continue

        emitted_response_tokens = True
        yield content

    if emitted_response_tokens:
        return

    result = agent.get_state(config).values
    final_message = result.get("messages", [])[-1] if result.get("messages") else None
    fallback = getattr(final_message, "content", "")
    if fallback:
        yield fallback


async def activate_agent_stream_async(user_input, agent, *, thread_id: str, recursion_limit: int = DEFAULT_RECURSION_LIMIT):
    """Stream the final assistant response from the agent graph asynchronously."""
    config = _agent_config(thread_id, recursion_limit)
    emitted_response_tokens = False

    async for token, metadata in agent.astream(_initial_state(user_input), config=config, stream_mode="messages"):
        if metadata.get("langgraph_node") != "response_node":
            continue

        content = getattr(token, "content", "")
        if not content:
            continue

        emitted_response_tokens = True
        yield content

    if emitted_response_tokens:
        return

    result = (await agent.aget_state(config)).values
    final_message = result.get("messages", [])[-1] if result.get("messages") else None
    fallback = getattr(final_message, "content", "")
    if fallback:
        yield fallback


def _agent_config(thread_id: str, recursion_limit: int = DEFAULT_RECURSION_LIMIT):
    return {
        "recursion_limit": recursion_limit,
        "configurable": {"thread_id": thread_id},
    }

#
def _initial_state(user_input):
    return {
        "messages": [HumanMessage(content=user_input)],
        "context": app_context,
        "current_year": date.today().year,
        "available_tools": _serialize_tools(),
    }


def router(state: AgentState):
    print("Router Node Activated")
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

    answer = route_text or "I can help with public-company valuation and financial analysis. What company or ticker would you like to analyze?"
    return {
        "messages": [AIMessage(content=answer)],
        "router_route": "end",
    }


async def arouter(state: AgentState):
    print("Router Node Activated")
    try:
        router_message = await _ainvoke_llm(state, router_prompt)
    except Exception as exc:
        return {
            "messages": [AIMessage(content=f"I could not route the request reliably: {exc}")],
            "router_route": "end",
        }

    route_text = (router_message.content or "").strip()
    if route_text == "plan_node":
        return {"router_route": "plan_node"}

    answer = route_text or "I can help with public-company valuation and financial analysis. What company or ticker would you like to analyze?"
    return {
        "messages": [AIMessage(content=answer)],
        "router_route": "end",
    }


def _tool_results_since_last_human(state) -> bool:
    for m in reversed(state.get("messages", [])):
        if isinstance(m, HumanMessage):
            return False
        if isinstance(m, ToolMessage):
            return True
    return False

def plan_node(state: AgentState):
    plan_message = _invoke_llm(state, plan_prompt, use_tools=True)
    if getattr(plan_message, "tool_calls", None):
        return {"messages": [plan_message], "plan_status": "needs_tools"}

    # No tool calls — only valid if we already gathered data this turn
    if _tool_results_since_last_human(state):
        return {"plan_status": "ready_to_respond"}

    # Model produced filler without acting → force it to plan tools
    forced = _invoke_llm(state, plan_prompt, use_tools=True, force_tools=True)
    if getattr(forced, "tool_calls", None):
        return {"messages": [forced], "plan_status": "needs_tools"}

    return {"plan_status": "ready_to_respond"}  # give up gracefully, don't loop


async def aplan_node(state: AgentState):
    print("Plan Node Activated")
    try:
        plan_message = await _ainvoke_llm(state, plan_prompt, use_tools=True)
    except Exception as exc:
        return {
            "messages": [AIMessage(content=f"I could not create a valid tool plan: {exc}")],
            "plan_status": "ready_to_respond",
        }

    _print_tool_calls("Execution Plan", plan_message)
    if getattr(plan_message, "tool_calls", None):
        return {"messages": [plan_message], "plan_status": "needs_tools"}

    if _tool_results_since_last_human(state):
        return {"plan_status": "ready_to_respond"}

    try:
        forced = await _ainvoke_llm(state, plan_prompt, use_tools=True, force_tools=True)
    except Exception as exc:
        return {
            "messages": [AIMessage(content=f"I could not create a valid tool plan: {exc}")],
            "plan_status": "ready_to_respond",
        }

    _print_tool_calls("Forced Execution Plan", forced)
    if getattr(forced, "tool_calls", None):
        return {"messages": [forced], "plan_status": "needs_tools"}

    return {"plan_status": "ready_to_respond"}


def response_node(state: AgentState):
    print("Response Node Activated")
    try:
        response_message = _invoke_llm(state, response_prompt)
    except Exception as exc:
        response_message = AIMessage(
            content=f"I gathered data but could not complete analysis: {exc}"
        )

    return {"messages": [response_message]}


async def aresponse_node(state: AgentState):
    print("Response Node Activated")
    try:
        response_message = await _ainvoke_llm(state, response_prompt)
    except Exception as exc:
        response_message = AIMessage(
            content=f"I gathered data but could not complete analysis: {exc}"
        )

    return {"messages": [response_message]}


async def _ainvoke_llm(state: AgentState, prompt: str, use_tools: bool = False, force_tools: bool = False) -> AIMessage:
    context = {
        "latest_user_message": _latest_human_message_content(state),
        "current_year": state.get("current_year"),
        "available_tools": state["available_tools"],
    }
    system_prompt = _system_prompt(
        app_context=state.get("context", ""),
        node_prompt=prompt,
        runtime_context=context,
    )
    if use_tools:
        model = CHAT_MODEL.bind_tools(tools, tool_choice="any" if force_tools else "auto")
    else:
        model = CHAT_MODEL
    return await model.ainvoke([SystemMessage(content=system_prompt)] + state["messages"])


def _route_after_router(state: AgentState) -> str:
    return state.get("router_route", "end")


def _route_after_plan(state: AgentState) -> str:
    if state.get("plan_status") == "needs_tools":
        return "tools"

    return "response_node"



def _invoke_llm(state: AgentState, prompt: str, use_tools: bool = False, force_tools: bool = False) -> AIMessage:
    context = {
        "latest_user_message": _latest_human_message_content(state),
        "current_year": state.get("current_year"),
        "available_tools": state["available_tools"],
    }
    system_prompt = _system_prompt(
        app_context=state.get("context", ""),
        node_prompt=prompt,
        runtime_context=context,
    )
    if use_tools:
        model = CHAT_MODEL.bind_tools(tools, tool_choice="any" if force_tools else "auto")
    else:
        model = CHAT_MODEL
    return model.invoke([SystemMessage(content=system_prompt)] + state["messages"])


def _system_prompt(app_context: str, node_prompt: str, runtime_context: dict) -> str:
    return f"""
    Universal agent instructions:
    {app_context}

    Node instructions:
    {node_prompt}

    Runtime context:
    {json.dumps(runtime_context, indent=2, default=str)}
    """


def _print_tool_calls(label: str, message: AIMessage) -> None:
    tool_calls = getattr(message, "tool_calls", None) or []
    if tool_calls:
        print(f"{label}:")
        print(json.dumps(tool_calls, indent=2, default=str))


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
