import asyncio
import json
import logging
from copy import deepcopy
from datetime import date
from typing import Any, Literal

from langchain.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from .cache import (
    build_data_catalog,
    empty_data_catalog,
    state_cache,
    tool_content,
)
from .prompts import (
    app_context,
    plan_prompt,
    response_prompt,
    router_prompt,
)
from .state import CHAT_MODEL, AgentState, merge_cache
from .tools import tools

logger = logging.getLogger(__name__)


class RouterDecision(BaseModel):
    route: Literal["plan_node", "end"]
    answer: str | None = None


DEFAULT_RECURSION_LIMIT = 12

GROUP_LABELS: dict[str, str] = {
    "financial_statement": "Fetching financial statements...",
    "market_data": "Fetching market data...",
    "sector_data": "Fetching sector data...",
    "growth_rate": "Calculating growth rates...",
    "ratio": "Calculating ratios...",
    "dcf": "Running DCF valuation...",
}

_GROUP_PRIORITY: list[str] = [
    "financial_statement",
    "market_data",
    "sector_data",
    "growth_rate",
    "ratio",
    "dcf",
]


def _serialize_tools():
    serialized = {"research": [], "calculation": []}
    for tool in tools:
        metadata = (getattr(tool, "metadata", None) or {}).get("agent", {})
        phase = metadata.get("phase", "calculation")
        entry = {
            "name": tool.name,
            "description": getattr(tool, "description", "") or "",
            "args": getattr(tool, "args", {}) or {},
            "metadata": metadata,
        }
        serialized.setdefault(phase, []).append(entry)

    return serialized


_AVAILABLE_TOOLS = _serialize_tools()
_TOOLS_BY_NAME = {tool.name: tool for tool in tools}


def initialize_agent():
    agent_builder = StateGraph(AgentState)

    agent_builder.add_node("router", router)
    agent_builder.add_node("plan_node", plan_node)
    agent_builder.add_node("tools", tools_node)
    agent_builder.add_node("response_node", response_node)

    agent_builder.add_edge(START, "router")
    agent_builder.add_conditional_edges("router", _route_after_router, {"plan_node": "plan_node", "end": END})
    agent_builder.add_conditional_edges("plan_node", _route_after_plan, {"tools": "tools", "response_node": "response_node"})
    agent_builder.add_edge("tools", "plan_node")
    agent_builder.add_edge("response_node", END)

    return agent_builder.compile(checkpointer=MemorySaver())


def activate_agent(
    user_input,
    agent,
    *,
    thread_id: str,
    recursion_limit: int = DEFAULT_RECURSION_LIMIT,
    debug_updates: bool = False,
):
    return asyncio.run(
        activate_agent_async(
            user_input,
            agent,
            thread_id=thread_id,
            recursion_limit=recursion_limit,
            debug_updates=debug_updates,
        )
    )


async def activate_agent_async(
    user_input,
    agent,
    *,
    thread_id: str,
    recursion_limit: int = DEFAULT_RECURSION_LIMIT,
    debug_updates: bool = False,
):
    config = _agent_config(thread_id, recursion_limit)

    previous_state = await agent.aget_state(config)
    _set_turn_start_step(config, previous_state)
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


def activate_agent_stream(
    user_input,
    agent,
    *,
    thread_id: str,
    recursion_limit: int = DEFAULT_RECURSION_LIMIT,
):
    chunks = asyncio.run(
        _collect_agent_stream(
            user_input,
            agent,
            thread_id=thread_id,
            recursion_limit=recursion_limit,
        )
    )
    yield from chunks


async def _collect_agent_stream(
    user_input,
    agent,
    *,
    thread_id: str,
    recursion_limit: int = DEFAULT_RECURSION_LIMIT,
) -> list[str]:
    chunks = []
    async for chunk in activate_agent_stream_async(
        user_input,
        agent,
        thread_id=thread_id,
        recursion_limit=recursion_limit,
    ):
        chunks.append(chunk)
    return chunks


async def activate_agent_stream_async(
    user_input,
    agent,
    *,
    thread_id: str,
    recursion_limit: int = DEFAULT_RECURSION_LIMIT,
):
    """Stream the final assistant response from the agent graph asynchronously."""
    config = _agent_config(thread_id, recursion_limit)
    previous_state = await agent.aget_state(config)
    _set_turn_start_step(config, previous_state)
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


async def activate_agent_stream_events_async(
    user_input,
    agent,
    *,
    thread_id: str,
    recursion_limit: int = DEFAULT_RECURSION_LIMIT,
):
    """Yield structured progress events plus token-by-token response deltas.

    Event shapes:
      {"type": "thought", "content": "<human-readable step description>"}
      {"type": "status",  "text":    "<short progress label>"}
      {"type": "delta",   "content": "<response text>"}
    """
    config = _agent_config(thread_id, recursion_limit)
    previous_state = await agent.aget_state(config)
    _set_turn_start_step(config, previous_state)
    emitted_response_tokens = False
    emitted_delta = False
    emitted_status_texts: set[str] = set()

    async for mode, data in agent.astream(
        _initial_state(user_input),
        config=config,
        stream_mode=["updates", "messages"],
    ):
        if mode == "updates":
            for node_name, state_update in data.items():
                for event in _events_from_node_update(node_name, state_update):
                    if event["type"] == "status":
                        text = event.get("text", "")
                        if text in emitted_status_texts:
                            continue
                        emitted_status_texts.add(text)
                    if event["type"] == "delta":
                        emitted_delta = True
                    yield event
            continue

        token, metadata = data
        if metadata.get("langgraph_node") != "response_node":
            continue

        content = getattr(token, "content", "")
        if not content:
            continue

        if not emitted_response_tokens:
            yield {"type": "status", "text": "Almost ready..."}
            emitted_response_tokens = True

        emitted_delta = True
        yield {"type": "delta", "content": content}

    if emitted_delta:
        return

    result = (await agent.aget_state(config)).values
    final_message = result.get("messages", [])[-1] if result.get("messages") else None
    fallback = getattr(final_message, "content", "")
    if fallback:
        yield {"type": "delta", "content": fallback}


def _events_from_node_update(node_name: str, state_update: dict) -> list[dict]:
    """Translate a LangGraph node state delta into frontend event dicts."""
    events: list[dict] = []
    messages = state_update.get("messages", [])

    if node_name == "router":
        route = state_update.get("router_route", "end")
        if route == "plan_node":
            events.append({"type": "thought", "content": "Identified as a financial analysis request"})
        else:
            for msg in messages:
                content = getattr(msg, "content", "")
                if content:
                    events.append({"type": "delta", "content": content})

    elif node_name == "plan_node":
        forced = state_update.get("forced_response_due_to_recursion", False)
        plan_status = state_update.get("plan_status", "")
        if forced:
            events.append({"type": "thought", "content": "Recursion limit approaching - composing response with available data"})
        elif plan_status == "needs_tools":
            for msg in messages:
                tool_calls = getattr(msg, "tool_calls", None) or []
                if tool_calls:
                    events.extend(_status_events_from_tool_calls(tool_calls))
                    descs = [
                        "{name}({args})".format(
                            name=tc.get("name", ""),
                            args=", ".join(
                                f"{k}={v}" for k, v in (tc.get("args") or {}).items()
                            ),
                        )
                        for tc in tool_calls
                    ]
                    events.append({"type": "thought", "content": f"Requesting: {', '.join(descs)}"})
        elif plan_status == "ready_to_respond":
            events.append({"type": "thought", "content": "Sufficient data gathered - composing response"})

    elif node_name == "tools":
        retrieved: list[str] = []
        tool_names: list[str] = []
        for msg in messages:
            name = getattr(msg, "name", None) or ""
            if not name:
                continue
            tool_names.append(name)
            source = ""
            try:
                data = json.loads(getattr(msg, "content", "{}") or "{}")
                source = data.get("source", "")
            except Exception:
                pass
            retrieved.append(f"{name} [{source}]" if source else name)
        if retrieved:
            events.extend(_status_events_from_tool_names(tool_names))
            events.append({"type": "thought", "content": f"Retrieved: {', '.join(retrieved)}"})

    elif node_name == "response_node":
        if messages:
            events.append({"type": "thought", "content": "Composing response"})

    return events


def _status_events_from_tool_calls(tool_calls: list[dict]) -> list[dict]:
    tool_names = [tc.get("name", "") for tc in tool_calls]
    return _status_events_from_tool_names(tool_names)


def _status_events_from_tool_names(tool_names: list[str]) -> list[dict]:
    groups = {
        ((getattr(_TOOLS_BY_NAME.get(name), "metadata", None) or {}).get("agent", {}) or {}).get("group")
        for name in tool_names
    }
    return [
        {"type": "status", "text": GROUP_LABELS[group]}
        for group in _GROUP_PRIORITY
        if group in groups
    ]


def _agent_config(thread_id: str, recursion_limit: int = DEFAULT_RECURSION_LIMIT):
    return {
        "recursion_limit": recursion_limit,
        "configurable": {"thread_id": thread_id},
    }


def _set_turn_start_step(config: dict[str, Any], state_snapshot) -> None:
    metadata = getattr(state_snapshot, "metadata", None) or {}
    turn_start_step = metadata.get("step", -1)
    config.setdefault("configurable", {})["turn_start_step"] = turn_start_step


def _initial_state(user_input):
    return {
        "messages": [HumanMessage(content=user_input)],
        "context": app_context,
        "current_year": date.today().year,
        "available_tools": _AVAILABLE_TOOLS,
        "forced_response_due_to_recursion": False,
    }


async def router(state: AgentState):
    logger.info("Router Node Activated")
    try:
        decision: RouterDecision = await _invoke_llm_structured(state, router_prompt, RouterDecision)
    except Exception as exc:
        return {
            "messages": [AIMessage(content=f"I could not route the request reliably: {exc}")],
            "router_route": "end",
        }

    if decision.route == "plan_node":
        return {"router_route": "plan_node"}

    answer = decision.answer or "I can help with public-company valuation and financial analysis. What company or ticker would you like to analyze?"
    return {
        "messages": [AIMessage(content=answer)],
        "router_route": "end",
    }


async def plan_node(state: AgentState, config: RunnableConfig):
    logger.info("Plan Node Activated")
    if _should_force_response(config):
        return {
            "plan_status": "ready_to_respond",
            "forced_response_due_to_recursion": True,
        }

    try:
        plan_message = await _invoke_llm(state, plan_prompt, use_tools=True)
    except Exception as exc:
        return {
            "messages": [AIMessage(content=f"I could not create a valid tool plan: {exc}")],
            "plan_status": "ready_to_respond",
        }

    _log_tool_calls("Execution Plan", plan_message)
    if getattr(plan_message, "tool_calls", None):
        return {
            "messages": [plan_message],
            "plan_status": "needs_tools",
        }

    return {"plan_status": "ready_to_respond"}


async def tools_node(state: AgentState):
    logger.info("Tools Node Activated")
    tool_calls = _latest_tool_calls(state)
    grouped_calls = _group_calls_by_ticker(tool_calls)
    base_cache = state_cache(state)
    messages: list[ToolMessage] = []

    global_calls = grouped_calls.pop(None, [])
    if global_calls:
        global_result = await _run_ticker_group(None, global_calls, base_cache)
        messages.extend(global_result["messages"])
        base_cache = global_result["data_cache"]

    group_results = await asyncio.gather(
        *[
            _run_ticker_group(ticker, calls, base_cache)
            for ticker, calls in grouped_calls.items()
        ]
    )

    merged_cache = base_cache
    for result in group_results:
        messages.extend(result["messages"])
        merged_cache = merge_cache(merged_cache, result["data_cache"])

    return {
        "messages": messages,
        "data_cache": merged_cache,
        "data_catalog": build_data_catalog(merged_cache),
    }


async def _run_ticker_group(
    ticker: str | None,
    calls: list[dict[str, Any]],
    data_cache: dict[str, Any],
) -> dict[str, Any]:
    cache = deepcopy(data_cache)
    messages = []
    for call in calls:
        name = call.get("name")
        args = dict(call.get("args") or {})
        tool_call_id = call.get("id") or ""
        tool = _TOOLS_BY_NAME.get(name)
        if tool is None:
            content = json.dumps(
                {
                    "error": f"Unknown tool: {name}",
                    "available_tools": sorted(_TOOLS_BY_NAME),
                }
            )
            messages.append(ToolMessage(content=content, name=name, tool_call_id=tool_call_id))
            continue

        try:
            result = await asyncio.to_thread(
                tool.invoke,
                {**args, "data_cache": cache},
            )
            content = tool_content(result)
        except Exception as exc:
            content = f"Tool execution failed for {name}: {exc}"

        messages.append(ToolMessage(content=content, name=name, tool_call_id=tool_call_id))

    return {
        "messages": messages,
        "data_cache": cache,
    }


def _group_calls_by_ticker(tool_calls: list[dict[str, Any]]) -> dict[str | None, list[dict[str, Any]]]:
    grouped: dict[str | None, list[dict[str, Any]]] = {}
    for call in tool_calls:
        args = call.get("args") or {}
        ticker = args.get("ticker")
        key = str(ticker).strip().upper() if ticker else None
        grouped.setdefault(key, []).append(call)
    return grouped


async def response_node(state: AgentState):
    logger.info("Response Node Activated")
    try:
        response_message = await _invoke_llm(state, response_prompt)
    except Exception as exc:
        response_message = AIMessage(
            content=f"I gathered data but could not complete analysis: {exc}"
        )

    return {"messages": [response_message]}


def _route_after_router(state: AgentState) -> str:
    return state.get("router_route", "end")


def _route_after_plan(state: AgentState) -> str:
    if state.get("plan_status") == "needs_tools":
        return "tools"

    return "response_node"


def _should_force_response(config: RunnableConfig) -> bool:
    current_step = (config.get("metadata") or {}).get("langgraph_step")
    if current_step is None:
        return False

    turn_start_step = (config.get("configurable") or {}).get("turn_start_step", -1)
    recursion_limit = config.get("recursion_limit", DEFAULT_RECURSION_LIMIT)
    turn_step = int(current_step) - int(turn_start_step)
    return turn_step >= recursion_limit - 2


async def _invoke_llm(state: AgentState, prompt: str, use_tools: bool = False) -> AIMessage:
    system_prompt = _build_system_prompt(state, prompt)
    model = CHAT_MODEL.bind_tools(tools) if use_tools else CHAT_MODEL
    return await model.ainvoke([SystemMessage(content=system_prompt)] + _messages_for_llm(state))


async def _invoke_llm_structured(state: AgentState, prompt: str, schema: type) -> Any:
    system_prompt = _build_system_prompt(state, prompt)
    model = CHAT_MODEL.with_structured_output(schema)
    return await model.ainvoke([SystemMessage(content=system_prompt)] + _messages_for_llm(state))


def _build_system_prompt(state: AgentState, node_prompt: str) -> str:
    context = {
        "latest_user_message": _latest_human_message_content(state),
        "current_year": state.get("current_year"),
        "available_tools": state["available_tools"],
        "cached_data_catalog": state.get("data_catalog", empty_data_catalog()),
        "forced_response_due_to_recursion": state.get("forced_response_due_to_recursion", False),
    }
    return f"""
    Universal agent instructions:
    {state.get("context", "")}

    Node instructions:
    {node_prompt}

    Runtime context:
    {json.dumps(context, indent=2, default=str)}
    """


def _log_tool_calls(label: str, message: AIMessage) -> None:
    tool_calls = getattr(message, "tool_calls", None) or []
    if tool_calls:
        logger.debug("%s: %s", label, json.dumps(tool_calls, indent=2, default=str))


def _latest_human_message_content(state) -> str:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage):
            return message.content

    return ""


def _latest_tool_calls(state) -> list[dict]:
    for message in reversed(state.get("messages", [])):
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            return tool_calls

    return []


def _messages_for_llm(state) -> list:
    messages = state.get("messages", [])
    last_tool_call_ai_index = None
    last_final_ai_index = None

    for index, message in enumerate(messages):
        if not isinstance(message, AIMessage):
            continue
        if getattr(message, "tool_calls", None):
            last_tool_call_ai_index = index
        else:
            last_final_ai_index = index

    include_active_tool_block = (
        last_tool_call_ai_index is not None
        and (
            last_final_ai_index is None
            or last_tool_call_ai_index > last_final_ai_index
        )
    )

    filtered = []
    for index, message in enumerate(messages):
        if include_active_tool_block and index >= last_tool_call_ai_index:
            filtered.append(message)
            continue

        if getattr(message, "type", None) == "tool":
            continue
        if getattr(message, "tool_calls", None):
            continue

        filtered.append(message)

    return filtered
