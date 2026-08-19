"""Insight node: interprets each of this batch's tool results with parallel LLM calls.

Runs between exec_calc and react. Each call sees exactly one tool result plus the
user query and the plan rationale, so interpretation quality does not degrade with
batch size and react stays a pure scheduling node.
"""

import asyncio
import logging

from langchain_core.messages import ToolMessage
from pydantic import BaseModel

from backend.core.llm import message_text

from ..llm import invoke_llm_structured
from ..messages import current_tool_block, latest_human_message_content
from ..prompts import insight_prompt
from ..state import AgentState
from ..tools import TOOLS_BY_NAME

logger = logging.getLogger(__name__)


class InsightNote(BaseModel):
    # Empty string means the result carried nothing worth noting — entry is skipped.
    insight: str = ""


async def insight_node(state: AgentState):
    """Write one interpretation per tool result in this batch, concurrently."""
    logger.info("Insight Node Activated")

    tool_messages = [m for m in current_tool_block(state) if isinstance(m, ToolMessage)]
    if not tool_messages:
        return {}

    user_query = latest_human_message_content(state)
    plan_rationale = state.get("tool_guidance", "")
    # Insights carry the cycle react is about to record for this batch, and the
    # user query index so downstream context can be scoped per turn.
    cycle = state.get("react_iterations", 0) + 1
    query_index = state.get("query_count", 0)

    async def _note_for(msg: ToolMessage) -> dict | None:
        try:
            note: InsightNote = await invoke_llm_structured(
                state,
                insight_prompt,
                InsightNote,
                node="insight",
                messages=[],
                extra_context={
                    "tool_name": msg.name,
                    "tool_result": message_text(msg),
                    "user_query": user_query,
                    "plan_rationale": plan_rationale,
                },
            )
        except Exception as exc:
            logger.warning("Insight generation failed for %s: %s", msg.name, exc)
            return None
        text = note.insight.strip()
        if not text:
            return None
        tool = TOOLS_BY_NAME.get(msg.name)
        group = ((getattr(tool, "metadata", None) or {}).get("agent", {}) or {}).get("group")
        return {
            "tool_name": msg.name,
            "group": group,
            "insight": text,
            "cycle": cycle,
            "query_index": query_index,
        }

    notes = await asyncio.gather(*[_note_for(m) for m in tool_messages])
    entries = [n for n in notes if n]
    return {"tool_insights": entries} if entries else {}
