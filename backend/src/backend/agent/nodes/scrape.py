"""Scrape node: expands scrape topics into queries and gathers web results."""

import asyncio
import json
import logging

from langchain_core.messages import ToolMessage
from pydantic import BaseModel

from backend.services.scrape import search_and_scrape_async

from ..constants import SCRAPE_LIMIT, SCRAPE_MIN_CONFIDENCE, SCRAPE_TOOL_NAME
from ..llm import invoke_llm_structured
from ..messages import latest_human_message_content, latest_tool_calls
from ..prompts import scrape_prompt
from ..state import AgentState

logger = logging.getLogger(__name__)


class ScrapeDecision(BaseModel):
    """Structured research plan for web scraping queries."""

    queries: list[str]
    research_goal: str = ""
    preferred_source_types: list[str] = []
    avoid: list[str] = []


async def scrape_node(state: AgentState):
    logger.info("Scrape Node Activated")
    tool_calls = latest_tool_calls(state)
    scrape_calls = [tc for tc in tool_calls if tc.get("name") == SCRAPE_TOOL_NAME]

    async def _process_one(call: dict) -> tuple[ToolMessage, list[dict]]:
        args = call.get("args") or {}
        topic = args.get("topic", "")
        max_results = min(int(args.get("max_results", 3)), SCRAPE_LIMIT)
        tool_call_id = call.get("id") or ""

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


        async def _run_query(query: str) -> tuple[str, list, Exception | None]:
            try:
                hits = await search_and_scrape_async(
                    query,
                    max_results,
                    avoid=avoid,
                    research_goal=research_goal,
                    preferred_source_types=preferred_source_types,
                )
                return query, hits, None
            except Exception as exc:
                return query, [], exc

        query_results = await asyncio.gather(*[_run_query(q) for q in queries])

        all_results: list[dict] = []
        new_entries_local: list[dict] = []
        for query, hits, exc in query_results:
            if exc is not None:
                logger.warning("Scrape failed for query %r: %s", query, exc)
                continue
            for r in hits:
                # One threshold for both channels: anything below it neither
                # reaches the LLM's tool message nor scrape_history — the model
                # must never cite a result that won't persist into later cycles.
                if r.confidence < SCRAPE_MIN_CONFIDENCE:
                    continue
                entry = {
                    "query": query,
                    "url": r.url,
                    "title": r.title,
                    "snippet": r.snippet,
                    "confidence": r.confidence,
                    "source_type": r.source_type,
                }
                all_results.append(entry)
                new_entries_local.append(entry)

        # Deduplicate by URL — keep highest-confidence entry per URL
        seen: dict[str, dict] = {}
        for entry in all_results:
            url = entry["url"]
            if url not in seen or entry["confidence"] > seen[url]["confidence"]:
                seen[url] = entry
        top = sorted(seen.values(), key=lambda x: x["confidence"], reverse=True)[:5]
        content = json.dumps(
            {"source": "web", "research_goal": research_goal, "queries": queries, "results": top},
            default=str,
        )
        return ToolMessage(content=content, name=SCRAPE_TOOL_NAME, tool_call_id=tool_call_id), new_entries_local

    call_results = await asyncio.gather(*[_process_one(call) for call in scrape_calls])

    messages: list[ToolMessage] = []
    new_entries: list[dict] = []
    for msg, entries in call_results:
        messages.append(msg)
        new_entries.extend(entries)

    return {
        "messages": messages,
        "scrape_history": new_entries,
    }


async def _invoke_scrape_decision(state: AgentState, topic: str) -> ScrapeDecision:
    """Generate a ScrapeDecision using a clean prompt with no prior message history.

    Passes messages=[] instead of reusing state["messages"], so the model never
    sees the unresolved tool_calls from the plan message, which would cause an
    API validation error. Provider compatibility (system prompt format,
    structured-output fallbacks) is handled by invoke_llm_structured.
    """
    return await invoke_llm_structured(
        state,
        scrape_prompt,
        ScrapeDecision,
        node="scrape",
        messages=[],
        extra_context={
            "latest_user_message": latest_human_message_content(state),
            "topic": topic,
        },
    )
