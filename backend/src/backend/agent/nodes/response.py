"""Response node: composes the final user-facing answer from research/calculated messages."""

import logging
import re
from typing import Any

from langchain_core.messages import AIMessage

from ..llm import invoke_llm
from ..prompts import deep_response_prompt, judge_response_addendum, response_prompt
from ..state import AgentState
from ..tools import TOOLS_BY_NAME

logger = logging.getLogger(__name__)

TOOL_METHODOLOGY_LABELS: dict[str, str] = {
    "get_financials": "Financial statement data",
    "get_market_data": "Market data",
    "get_sector_data": "Sector valuation assumptions",
    "get_income_statement_growth_rates": "Income statement growth calculations",
    "get_balance_sheet_growth_rates": "Balance sheet growth calculations",
    "get_liquidity_ratios": "Liquidity ratio calculations",
    "get_solvency_ratios": "Solvency ratio calculations",
    "get_profitability_ratios": "Profitability ratio calculations",
    "get_efficiency_ratios": "Efficiency ratio calculations",
    "run_dcf_valuation": "DCF valuation model",
    "get_comps_valuation": "Comparable valuation model",
    "scrape_web": "Web research",
}

IDENTIFIER_METHODOLOGY_LABELS: dict[str, str] = {
    "financials": "Financial statement data",
    "market_data": "Market data",
    "sector_data": "Sector valuation assumptions",
    "damodaran_sector": "Sector valuation assumptions",
    "growth": "Growth calculations",
    "ratios": "Ratio calculations",
    "dcf": "DCF valuation model",
    "comparables": "Comparable valuation model",
}

_GENERIC_INTERNAL_NAME_PATTERN = re.compile(r"\b[a-z][a-z0-9]*_(?:[a-z0-9_]*_)?(?:func|tool)\b")


def _methodology_label(entry: dict[str, Any]) -> str:
    tool_name = str(entry.get("tool") or "")
    if tool_name in TOOL_METHODOLOGY_LABELS:
        return TOOL_METHODOLOGY_LABELS[tool_name]

    identifier = entry.get("identifier") or ()
    kind = ""
    if isinstance(identifier, (list, tuple)) and identifier:
        kind = str(identifier[0])
    return IDENTIFIER_METHODOLOGY_LABELS.get(kind, "Data retrieval/calculation")


def _sanitize_internal_names(text: str) -> str:
    """Replace backend tool identifiers with user-facing labels before response LLMs see them."""
    cleaned = text
    for internal_name, public_label in sorted(
        TOOL_METHODOLOGY_LABELS.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        cleaned = re.sub(rf"\b{re.escape(internal_name)}\s*\([^)]*\)", public_label, cleaned)
        cleaned = re.sub(rf"\b{re.escape(internal_name)}\b", public_label, cleaned)
    return _GENERIC_INTERNAL_NAME_PATTERN.sub("internal calculation", cleaned)


def _project(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop bookkeeping fields (tool, cycle, last_updated) the LLM doesn't need.

    Keeps data_source so the LLM cites the real upstream provenance (e.g. "SEC
    EDGAR") instead of inferring it from the internal tool name.
    """
    return [
        {
            "ticker": e["ticker"],
            "identifier": e["identifier"],
            "data": e["data"],
            "data_source": e.get("data_source"),
            "methodology_label": _methodology_label(e),
        }
        for e in entries
    ]


def _methodology_notes(entries: list[dict[str, Any]]) -> dict[str, str]:
    notes: dict[str, str] = {}
    for entry in entries:
        tool_name = str(entry.get("tool") or "")
        tool = TOOLS_BY_NAME.get(tool_name)
        if tool is None:
            continue

        label = _methodology_label(entry)
        description = getattr(tool, "description", "") or ""
        if description:
            notes[label] = _sanitize_internal_names(description)
    return notes


async def response_node(state: AgentState):
    """Generate the final user-facing answer from messages and gathered data."""
    logger.info("Response Node Activated")

    #Builds prompt; append judge critique instruction and prior response after a judge revision
    local_prompt = deep_response_prompt if state.get("deep_plan") else response_prompt
    if state.get("judge_verdict") == "revise":
        local_prompt = local_prompt + judge_response_addendum
        if cr := state.get("current_response"):
            local_prompt += (
                "\n\nYour previous response that must be completely rewritten:\n"
                f"{_sanitize_internal_names(cr)}"
            )

    #Reads every research/calculated entry currently known this conversation — full
    #content, not windowed to the latest tool-calling round, and not summarized.
    raw_research = state.get("research_messages", [])
    raw_calculated = state.get("calculated_messages", [])
    payload = {
        "research": _project(raw_research),
        "calculated": _project(raw_calculated),
    }

    #Surfaces each tool's own docstring (timeframe conventions, null-field caveats,
    #averaging behavior, etc.) for only the tools that actually produced data this
    #conversation — self-updating, since it reads the live docstring rather than a
    #copy maintained in the prompt.
    if notes := _methodology_notes([*raw_research, *raw_calculated]):
        payload = {**payload, "methodology": notes}

    #Gets access to plan node's rationale for tool selection and appends it to payload
    if guidance := state.get("tool_guidance"):
        payload = {**payload, "analysis_plan": _sanitize_internal_names(guidance)}

    #After a judge revision, surface its critique directly in gathered_data.
    if state.get("judge_verdict") == "revise" and (rationale := state.get("judge_rationale")):
        payload = {**payload, "judge_critique": _sanitize_internal_names(rationale)}

    #Invokes llm with system prompt and payload
    try:
        response_message = await invoke_llm(state, local_prompt, node="response", data_payload=payload)
    except Exception as exc:
        response_message = AIMessage(
            content=f"I gathered data but could not complete analysis: {exc}"
        )
    
    #Returns response and stores it as current_response for judge/react to reference
    content = response_message.content
    if isinstance(content, list):
        content = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    result = {}
    if content:
        result["current_response"] = content
    return result
