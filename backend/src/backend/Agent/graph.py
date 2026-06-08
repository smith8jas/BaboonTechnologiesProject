import asyncio
import json
import logging
from copy import deepcopy
from datetime import date
from typing import Any, Literal

from langchain.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from pydantic import BaseModel

from .cache import (
    build_data_catalog,
    build_data_payload,
    empty_data_catalog,
    state_cache,
    tool_content,
)
from backend.services.scrape import search_and_scrape_async
from .prompts import (
    app_context,
    data_dictionary,
    router_prompt,
    plan_prompt,
    deep_plan_prompt,
    response_prompt,
    deep_response_prompt,
    scrape_prompt
)
from .state import CHAT_MODEL, AgentState, merge_cache
from .tools import tools

logger = logging.getLogger(__name__)


class RouterDecision(BaseModel):
    route: Literal["plan_node", "end"]
    Deep_Plan: bool = False
    answer: str | None = None


class ScrapeDecision(BaseModel):
    queries: list[str]
    research_goal: str = ""
    preferred_source_types: list[str] = []
    avoid: list[str] = []


_SCRAPE_TOOL_NAME = "scrape_web"
_SCRAPE_MIN_CONFIDENCE = 0.3

DEFAULT_RECURSION_LIMIT = 12
SCRAPE_LIMIT = 10

Deep_Plan: bool = False

GROUP_LABELS: dict[str, str] = {
    "financial_statement": "Fetching financial statements...",
    "market_data": "Fetching market data...",
    "sector_data": "Fetching sector data...",
    "growth_rate": "Calculating growth rates...",
    "ratio": "Calculating ratios...",
    "dcf": "Running DCF valuation...",
    "web_scrape": "Searching the web...",
}

_GROUP_PRIORITY: list[str] = [
    "financial_statement",
    "market_data",
    "sector_data",
    "growth_rate",
    "ratio",
    "dcf",
    "web_scrape",
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
    agent_builder.add_node("scrape_node", scrape_node)
    agent_builder.add_node("response_node", response_node)

    agent_builder.add_edge(START, "router")
    agent_builder.add_conditional_edges("router", _route_after_router, {"plan_node": "plan_node", "end": END})
    agent_builder.add_conditional_edges(
        "plan_node",
        _route_after_plan,
        {"tools": "tools", "scrape_node": "scrape_node", "response_node": "response_node"},
    )
    agent_builder.add_edge("tools", "plan_node")
    agent_builder.add_edge("scrape_node", "plan_node")
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
        elif plan_status == "needs_scrape":
            for msg in messages:
                tool_calls = getattr(msg, "tool_calls", None) or []
                scrape_calls = [tc for tc in tool_calls if tc.get("name") == _SCRAPE_TOOL_NAME]
                if scrape_calls:
                    events.append({"type": "status", "text": GROUP_LABELS["web_scrape"]})
                    topics = [tc.get("args", {}).get("topic", "") for tc in scrape_calls if tc.get("args", {}).get("topic")]
                    desc = f"Web search queued: {', '.join(topics)}" if topics else "Web search queued"
                    events.append({"type": "thought", "content": desc})
        elif plan_status == "needs_scrape_and_tools":
            for msg in messages:
                tool_calls = getattr(msg, "tool_calls", None) or []
                if tool_calls:
                    non_scrape = [tc for tc in tool_calls if tc.get("name") != _SCRAPE_TOOL_NAME]
                    scrape_calls = [tc for tc in tool_calls if tc.get("name") == _SCRAPE_TOOL_NAME]
                    if non_scrape:
                        events.extend(_status_events_from_tool_calls(non_scrape))
                        descs = [
                            "{name}({args})".format(
                                name=tc.get("name", ""),
                                args=", ".join(
                                    f"{k}={v}" for k, v in (tc.get("args") or {}).items()
                                ),
                            )
                            for tc in non_scrape
                        ]
                        events.append({"type": "thought", "content": f"Requesting: {', '.join(descs)}"})
                    if scrape_calls:
                        events.append({"type": "status", "text": GROUP_LABELS["web_scrape"]})
                        topics = [tc.get("args", {}).get("topic", "") for tc in scrape_calls if tc.get("args", {}).get("topic")]
                        desc = f"Web search queued: {', '.join(topics)}" if topics else "Web search queued"
                        events.append({"type": "thought", "content": desc})
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

    elif node_name == "scrape_node":
        scrape_msgs = [m for m in messages if getattr(m, "name", None) == _SCRAPE_TOOL_NAME]
        if scrape_msgs:
            events.append({"type": "status", "text": "Searching the web..."})
            events.append({"type": "thought", "content": f"Web search completed ({len(scrape_msgs)} topic(s) scraped)"})

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
    global Deep_Plan
    logger.info("Router Node Activated")
    try:
        decision: RouterDecision = await _invoke_llm_structured(state, router_prompt, RouterDecision)
    except Exception as exc:
        Deep_Plan = False
        return {
            "messages": [AIMessage(content=f"I could not route the request reliably: {exc}")],
            "router_route": "end",
        }

    if decision.route == "plan_node":
        Deep_Plan = decision.Deep_Plan
        return {"router_route": "plan_node", "plan_iterations": 0}

    Deep_Plan = False
    answer = decision.answer or "I can help with public-company valuation and financial analysis. What company or ticker would you like to analyze?"
    return {
        "messages": [AIMessage(content=answer)],
        "router_route": "end",
    }


async def plan_node(state: AgentState):
    logger.info("Plan Node Activated")
    local_prompt = deep_plan_prompt if Deep_Plan else plan_prompt
    print(f"[PLAN] {'deep_plan_prompt' if Deep_Plan else 'plan_prompt'} active")
    plan_count = state.get("plan_iterations", 0)

    if plan_count >= DEFAULT_RECURSION_LIMIT - 2:
        return {
            "plan_status": "ready_to_respond",
            "forced_response_due_to_recursion": True,
        }

    next_count = plan_count + 1

    try:
        plan_message = await _invoke_llm(state, local_prompt, use_tools=True)
    except Exception as exc:
        return {
            "messages": [AIMessage(content=f"I could not create a valid tool plan: {exc}")],
            "plan_status": "ready_to_respond",
            "plan_iterations": next_count,
        }

    _log_tool_calls("Execution Plan", plan_message)
    tool_calls = getattr(plan_message, "tool_calls", None) or []
    if tool_calls:
        has_scrape = any(tc.get("name") == _SCRAPE_TOOL_NAME for tc in tool_calls)
        has_non_scrape = any(tc.get("name") != _SCRAPE_TOOL_NAME for tc in tool_calls)
        if has_scrape and has_non_scrape:
            return {
                "messages": [plan_message],
                "plan_status": "needs_scrape_and_tools",
                "plan_iterations": next_count,
            }
        if has_scrape:
            return {
                "messages": [plan_message],
                "plan_status": "needs_scrape",
                "plan_iterations": next_count,
            }
        return {
            "messages": [plan_message],
            "plan_status": "needs_tools",
            "plan_iterations": next_count,
        }

    return {"plan_status": "ready_to_respond", "plan_iterations": next_count}


async def tools_node(state: AgentState):
    logger.info("Tools Node Activated")
    tool_calls = [tc for tc in _latest_tool_calls(state) if tc.get("name") != _SCRAPE_TOOL_NAME]
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


async def scrape_node(state: AgentState):
    logger.info("Scrape Node Activated")
    print("[SCRAPE] scrape_node activated")
    tool_calls = _latest_tool_calls(state)
    scrape_calls = [tc for tc in tool_calls if tc.get("name") == _SCRAPE_TOOL_NAME]
    print(f"[SCRAPE] {len(scrape_calls)} scrape call(s)")

    messages: list[ToolMessage] = []
    new_entries: list[dict] = []

    for call in scrape_calls:
        args = call.get("args") or {}
        topic = args.get("topic", "")
        max_results = min(int(args.get("max_results", 3)), SCRAPE_LIMIT)
        tool_call_id = call.get("id") or ""
        print(f"[SCRAPE] Topic: {topic!r}  max_results={max_results}")

        # Use a clean system-only prompt to avoid sending unresolved tool_calls
        # from the plan message into the structured-output call.
        try:
            decision: ScrapeDecision = await _invoke_scrape_decision(state, topic)
            queries = decision.queries or [topic]
            research_goal = decision.research_goal or ""
            preferred_source_types = decision.preferred_source_types or []
            avoid = decision.avoid or []
        except Exception as exc:
            logger.warning("Scrape query generation failed: %s", exc)
            queries = [topic]
            research_goal = ""
            preferred_source_types = []
            avoid = []

        print(f"[SCRAPE] Expanded to {len(queries)} quer(ies): {queries}")
        print(f"[SCRAPE] goal={research_goal!r}  preferred={preferred_source_types}  avoid={avoid}")

        all_results: list[dict] = []
        for query in queries:
            try:
                hits = await search_and_scrape_async(
                    query,
                    max_results,
                    avoid=avoid,
                    research_goal=research_goal,
                    preferred_source_types=preferred_source_types,
                )
                print(f"[SCRAPE] Query {query!r}: {len(hits)} hit(s) returned")
                for r in hits:
                    print(f"[SCRAPE]   [{r.confidence:.3f}] [{r.source_type}] {r.title[:55]}  {r.url[:65]}")
                    entry = {
                        "query": query,
                        "url": r.url,
                        "title": r.title,
                        "snippet": r.snippet,
                        "confidence": r.confidence,
                        "source_type": r.source_type,
                    }
                    all_results.append(entry)
                    if r.confidence >= _SCRAPE_MIN_CONFIDENCE:
                        new_entries.append(entry)
            except Exception as exc:
                logger.warning("Scrape failed for query %r: %s", query, exc)
                print(f"[SCRAPE] ERROR for query {query!r}: {exc}")

        # Deduplicate by URL — keep highest-confidence entry per URL
        seen: dict[str, dict] = {}
        for entry in all_results:
            url = entry["url"]
            if url not in seen or entry["confidence"] > seen[url]["confidence"]:
                seen[url] = entry
        top = sorted(seen.values(), key=lambda x: x["confidence"], reverse=True)[:5]
        print(f"[SCRAPE] Top {len(top)} unique result(s) for tool message  ({len(new_entries)} added to history)")
        content = json.dumps(
            {
                "source": "web",
                "research_goal": research_goal,
                "queries": queries,
                "results": top,
            },
            default=str,
        )
        messages.append(ToolMessage(content=content, name=_SCRAPE_TOOL_NAME, tool_call_id=tool_call_id))

    return {
        "messages": messages,
        "scrape_history": new_entries,
    }


async def _invoke_scrape_decision(state: AgentState, topic: str) -> ScrapeDecision:
    """Generate a ScrapeDecision using a clean prompt with no prior message history.

    Bypasses _messages_for_llm entirely so the model never sees the unresolved
    tool_calls from the plan message, which would cause an API validation error.
    """
    system_content = (
        f"Universal agent instructions:\n{state.get('context', '')}\n\n"
        f"Node instructions:\n{scrape_prompt}\n\n"
        f"Runtime context:\n"
        + json.dumps(
            {
                "latest_user_message": _latest_human_message_content(state),
                "current_year": state.get("current_year"),
                "topic": topic,
            },
            indent=2,
        )
    )
    model = CHAT_MODEL.with_structured_output(ScrapeDecision)
    return await model.ainvoke([SystemMessage(content=system_content)])


async def response_node(state: AgentState):
    logger.info("Response Node Activated")
    local_prompt = deep_response_prompt if Deep_Plan else response_prompt
    payload = build_data_payload(state_cache(state))
    try:
        response_message = await _invoke_llm(state, local_prompt, data_payload=payload)
    except Exception as exc:
        response_message = AIMessage(
            content=f"I gathered data but could not complete analysis: {exc}"
        )

    return {"messages": [response_message]}


def _route_after_router(state: AgentState) -> str:
    return state.get("router_route", "end")


def _route_after_plan(state: AgentState):
    status = state.get("plan_status")
    if status == "needs_scrape_and_tools":
        return [Send("scrape_node", state), Send("tools", state)]
    if status == "needs_scrape":
        return "scrape_node"
    if status == "needs_tools":
        return "tools"
    return "response_node"



async def _invoke_llm(state: AgentState, prompt: str, use_tools: bool = False, data_payload: dict | None = None) -> AIMessage:
    system_prompt = _build_system_prompt(state, prompt, data_payload=data_payload)
    model = CHAT_MODEL.bind_tools(tools) if use_tools else CHAT_MODEL
    return await model.ainvoke([SystemMessage(content=system_prompt)] + _messages_for_llm(state))


async def _invoke_llm_structured(state: AgentState, prompt: str, schema: type) -> Any:
    system_prompt = _build_system_prompt(state, prompt)
    model = CHAT_MODEL.with_structured_output(schema)
    return await model.ainvoke([SystemMessage(content=system_prompt)] + _messages_for_llm(state))


def _build_system_prompt(state: AgentState, node_prompt: str, data_payload: dict | None = None) -> str:
    context = {
        "latest_user_message": _latest_human_message_content(state),
        "current_year": state.get("current_year"),
        "available_tools": state["available_tools"],
        "cached_data_catalog": state.get("data_catalog", empty_data_catalog()),
        "forced_response_due_to_recursion": state.get("forced_response_due_to_recursion", False),
        "scrape_history": state.get("scrape_history", [])[-20:],
    }
    if data_payload is not None:
        context["gathered_data"] = data_payload
    return f"""
    Universal agent instructions:
    {state.get("context", "")}

    Data dictionary:
    {data_dictionary}

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
