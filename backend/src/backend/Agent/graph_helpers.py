import json

from langchain.messages import HumanMessage, ToolMessage

from .state import tools, tools_by_name


def _single_tool_name(tool_names: set[str], label: str) -> str:
    if len(tool_names) != 1:
        raise RuntimeError(
            f"Expected exactly one {label} tool, found {sorted(tool_names)}."
        )

    return next(iter(tool_names))


def _agent_tool_metadata(tool) -> dict:
    return (getattr(tool, "metadata", None) or {}).get("agent", {})


def _tools_in_group(group: str) -> set[str]:
    return {
        tool.name
        for tool in tools
        if _agent_tool_metadata(tool).get("group") == group
    }


INITIAL_ROUTES = {"market_data", "sector_data", "financials"}
REACT_ROUTES = {"market_data", "sector_data", "financials", "growth_rates", "ratios"}
FINANCIAL_DEPENDENT_ROUTES = {"growth_rates", "ratios", "react_node"}
REACT_DECISION_ROUTES = {*REACT_ROUTES, "end"}

FINANCIAL_STATEMENT_TOOLS = _tools_in_group("financial_statement")
MARKET_DATA_TOOLS = _tools_in_group("market_data")
SECTOR_DATA_TOOLS = _tools_in_group("sector_data")
GROWTH_TOOLS = _tools_in_group("growth_rate")
RATIO_TOOLS = _tools_in_group("ratio")
GET_FINANCIALS = _single_tool_name(FINANCIAL_STATEMENT_TOOLS, "financial statement")
GET_MARKET_DATA = _single_tool_name(MARKET_DATA_TOOLS, "market data")
GET_SECTOR_DATA = _single_tool_name(SECTOR_DATA_TOOLS, "sector data")
TOOL_ROUTES = {
    tool.name: _agent_tool_metadata(tool).get("route")
    for tool in tools
    if _agent_tool_metadata(tool).get("route")
}


def serialize_tools():
    # Expose the registered LangChain tools in a JSON-friendly shape for prompts.
    return [
        {
            "name": tool.name,
            "description": getattr(tool, "description", "") or "",
            "args": getattr(tool, "args", {}) or {},
            "metadata": _agent_tool_metadata(tool),
        }
        for tool in tools
    ]


def serialize_tool_groups() -> dict[str, list[dict]]:
    # Expose tool groups so prompts do not hardcode tool names.
    return {
        "financial_statement_tools": _tool_summaries(FINANCIAL_STATEMENT_TOOLS),
        "market_data_tools": _tool_summaries(MARKET_DATA_TOOLS),
        "sector_data_tools": _tool_summaries(SECTOR_DATA_TOOLS),
        "growth_rate_tools": _tool_summaries(GROWTH_TOOLS),
        "ratio_tools": _tool_summaries(RATIO_TOOLS),
    }


def _tool_summaries(tool_names: set[str]) -> list[dict]:
    return [
        {
            "name": tool.name,
            "capability": _agent_tool_metadata(tool).get("capability", ""),
            "requires_financials": _agent_tool_metadata(tool).get(
                "requires_financials",
                False,
            ),
        }
        for tool in tools
        if tool.name in tool_names
    ]


def infer_route_from_tool_plan(tool_plan: list[dict]) -> str:
    # Choose the first graph node that should execute a planner-created tool plan.
    if not tool_plan:
        return "end"

    return route_for_tool(tool_plan[0].get("tool_name")) or "financials"


def infer_react_route_from_tool_plan(tool_plan: list[dict]) -> str:
    # Choose the next node requested by react when react adds more tool work.
    if not tool_plan:
        return "end"

    return route_for_tool(tool_plan[0].get("tool_name")) or "end"


def latest_human_message_content(state) -> str:
    # Find the latest user message so prompts can include the current request.
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage):
            return message.content

    return ""


def messages_for_llm(messages):
    # Remove ToolMessages before sending history back to OpenAI chat completions.
    return [message for message in messages if not isinstance(message, ToolMessage)]


def run_planned_tools(state, tool_names: set[str]) -> tuple[dict, list[ToolMessage]]:
    # Run planned tools whose inputs are already complete in the planner output.
    tool_results = dict(state.get("tool_results", {}))
    tool_messages = []

    for step in state.get("tool_plan", []):
        tool_name = step.get("tool_name")
        if tool_name not in tool_names or planned_step_done(step, tool_results):
            continue

        args = step.get("args") or {}
        result = tools_by_name[tool_name].invoke(args)
        tool_results.setdefault(tool_name, []).append({"args": args, "result": result})
        tool_messages.append(_tool_message(tool_name, args, result, tool_results))

    return tool_results, tool_messages


def run_financial_dependent_tools(
    state,
    tool_names: set[str],
) -> tuple[dict, list[ToolMessage]]:
    # Run ratio/growth tools by injecting financials gathered earlier in the flow.
    tool_results = dict(state.get("tool_results", {}))
    tool_messages = []
    financial_results = tool_results.get(GET_FINANCIALS, [])

    for step in state.get("tool_plan", []):
        tool_name = step.get("tool_name")
        if tool_name not in tool_names or planned_step_done(step, tool_results):
            continue

        matching_financials = _matching_financial_results(
            financial_results,
            _ticker_from_step_args(step.get("args") or {}),
        )
        if not matching_financials:
            tool_messages.append(
                ToolMessage(
                    content=(
                        f"Cannot run {tool_name}: no financials result is "
                        "available for the requested company."
                    ),
                    name=tool_name,
                    tool_call_id=f"{tool_name}-missing-financials",
                )
            )
            continue

        for financial_entry in matching_financials:
            args = _financial_dependent_args(tools_by_name[tool_name], financial_entry["result"])
            result = tools_by_name[tool_name].invoke(args)
            result_args = {"ticker": financial_entry.get("args", {}).get("ticker")}
            tool_results.setdefault(tool_name, []).append(
                {"args": result_args, "result": result}
            )
            tool_messages.append(_tool_message(tool_name, result_args, result, tool_results))

    return tool_results, tool_messages


def next_route_from_tool_plan(state, tool_results: dict) -> str:
    # Find the next unfinished planned tool and return the node that owns it.
    for step in state.get("tool_plan", []):
        if planned_step_done(step, tool_results):
            continue

        route = route_for_tool(step.get("tool_name"))
        if route:
            return route

    return "react_node"


def next_financial_dependent_route(state, tool_results: dict) -> str:
    # After financials run, route to unfinished ratio/growth work before react.
    for step in state.get("tool_plan", []):
        if planned_step_done(step, tool_results):
            continue

        route = route_for_tool(step.get("tool_name"))
        if route in {"growth_rates", "ratios"}:
            return route

    return "react_node"


def route_for_tool(tool_name: str) -> str | None:
    # Map a tool name to the graph node responsible for executing that tool.
    return TOOL_ROUTES.get(tool_name)


def planned_step_done(step: dict, tool_results: dict) -> bool:
    # Check whether a planned tool step already has a matching stored result.
    tool_name = step.get("tool_name")
    results = tool_results.get(tool_name, [])
    if not results:
        return False

    if route_for_tool(tool_name) in {"growth_rates", "ratios"}:
        requested_ticker = _ticker_from_step_args(step.get("args") or {})
        if not requested_ticker:
            return True

        return any(
            (entry.get("args", {}).get("ticker") or "").upper()
            == requested_ticker.upper()
            for entry in results
        )

    planned_args = _normalize_args(step.get("args") or {})
    return any(_normalize_args(entry.get("args") or {}) == planned_args for entry in results)


def extend_tool_plan(current_plan: list[dict], new_steps: list[dict]) -> list[dict]:
    # Append react-generated tool steps without duplicating existing work.
    extended_plan = list(current_plan)
    for step in new_steps:
        if step.get("tool_name") and not _plan_contains_step(extended_plan, step):
            extended_plan.append(step)

    return extended_plan


def tool_results_for_prompt(tool_results: dict) -> dict:
    # Convert stored tool results into JSON-safe data for react prompt context.
    return {
        tool_name: [
            {
                "args": entry.get("args", {}),
                "result": _json_safe_tool_result(entry.get("result")),
            }
            for entry in entries
        ]
        for tool_name, entries in tool_results.items()
    }


def fallback_react_answer(state) -> str:
    # Explain why react stopped when the LLM call limit prevents more work.
    gathered_tools = ", ".join(state.get("tool_results", {}).keys())
    if gathered_tools:
        return (
            "I reached the LLM call limit, so I cannot request more data. "
            f"I gathered results from: {gathered_tools}."
        )

    return "I reached the LLM call limit before gathering enough data to answer reliably."


def _tool_message(tool_name: str, args: dict, result, tool_results: dict) -> ToolMessage:
    # Wrap a raw tool result in a ToolMessage with debugging context.
    return ToolMessage(
        content=_format_tool_message_content(tool_name, args, result),
        name=tool_name,
        tool_call_id=f"{tool_name}-{len(tool_results[tool_name])}",
    )


def _normalize_args(args: dict) -> dict:
    # Reduce tool args to the fields used to compare duplicate planned steps.
    ticker = _ticker_from_step_args(args)
    if ticker:
        return {"ticker": ticker}

    return {
        key: value
        for key, value in args.items()
        if not isinstance(value, dict) or "$ref" not in value
    }


def _ticker_from_step_args(args: dict) -> str | None:
    # Extract a ticker from normal args or nested financials-style args.
    if args.get("ticker"):
        return args["ticker"]

    for key in ("financials", "hf"):
        value = args.get(key)
        if isinstance(value, dict) and value.get("ticker"):
            return value["ticker"]

    return None


def _plan_contains_step(tool_plan: list[dict], step: dict) -> bool:
    # Check whether a tool plan already contains the same tool and normalized args.
    step_name = step.get("tool_name")
    step_args = _normalize_args(step.get("args") or {})
    return any(
        existing.get("tool_name") == step_name
        and _normalize_args(existing.get("args") or {}) == step_args
        for existing in tool_plan
    )


def _json_safe_tool_result(result):
    # Convert Pydantic model results to dictionaries before prompt serialization.
    if hasattr(result, "model_dump"):
        return result.model_dump()

    return result


def _matching_financial_results(
    financial_results: list[dict],
    requested_ticker: str | None,
) -> list[dict]:
    # Select financial results for a specific ticker, or all when unspecified.
    if not requested_ticker:
        return financial_results

    return [
        entry
        for entry in financial_results
        if (entry.get("args", {}).get("ticker") or "").upper() == requested_ticker.upper()
    ]


def _financial_dependent_args(tool, financials) -> dict:
    # Build the expected input object for tools that depend on financial data.
    tool_args = getattr(tool, "args", {}) or {}
    if "hf" in tool_args:
        return {"hf": financials}
    if "financials" in tool_args:
        return {"financials": financials}

    return {"financials": financials}


def _format_tool_message_content(tool_name: str, args: dict, result) -> str:
    # Format tool messages so terminal output shows company/ticker context clearly.
    context = {
        "tool_name": tool_name,
        "ticker": _tool_result_ticker(args, result),
        "company": _tool_result_company(result),
        "args": args,
    }
    return (
        "Tool execution context:\n"
        f"{json.dumps(context, indent=2, default=str)}\n\n"
        "Tool result:\n"
        f"{_serialize_tool_result(result)}"
    )


def _tool_result_ticker(args: dict, result) -> str | None:
    # Get the ticker from tool args first, then from the returned object.
    if args.get("ticker"):
        return args["ticker"]
    if hasattr(result, "ticker"):
        return result.ticker

    return None


def _tool_result_company(result) -> str | None:
    # Get a company name from a tool result metadata object when available.
    metadata = getattr(result, "metadata", None)
    if metadata is not None:
        return getattr(metadata, "name", None)

    return None


def _serialize_tool_result(result) -> str:
    # Serialize tool output for readable ToolMessage content.
    if hasattr(result, "model_dump_json"):
        return result.model_dump_json(indent=2)

    try:
        return json.dumps(result, indent=2, default=str)
    except TypeError:
        return str(result)
