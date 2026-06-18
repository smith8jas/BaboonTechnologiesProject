"""Scrape node: expands scrape topics into queries and gathers web results."""

import asyncio
import json
import logging

from langchain_core.messages import SystemMessage, ToolMessage
from pydantic import BaseModel

from backend.core.llm import NODE_PROVIDERS, get_node_model
from backend.services.scrape import search_and_scrape_async

from ..constants import SCRAPE_LIMIT, SCRAPE_MIN_CONFIDENCE, SCRAPE_TOOL_NAME
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
    #print("[SCRAPE] scrape_node activated")
    tool_calls = latest_tool_calls(state)
    scrape_calls = [tc for tc in tool_calls if tc.get("name") == SCRAPE_TOOL_NAME]
    #print(f"[SCRAPE] {len(scrape_calls)} scrape call(s)")

    async def _process_one(call: dict) -> tuple[ToolMessage, list[dict]]:
        args = call.get("args") or {}
        topic = args.get("topic", "")
        max_results = min(int(args.get("max_results", 3)), SCRAPE_LIMIT)
        tool_call_id = call.get("id") or ""
        #print(f"[SCRAPE] Topic: {topic!r}  max_results={max_results}")

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

        #print(f"[SCRAPE] Expanded to {len(queries)} quer(ies)")

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
                #print(f"[SCRAPE] ERROR for query {query!r}: {exc}")
                continue
            #print(f"[SCRAPE] Query {query!r}: {len(hits)} hit(s) returned")
            for r in hits:
                entry = {
                    "query": query,
                    "url": r.url,
                    "title": r.title,
                    "snippet": r.snippet,
                    "confidence": r.confidence,
                    "source_type": r.source_type,
                }
                all_results.append(entry)
                if r.confidence >= SCRAPE_MIN_CONFIDENCE:
                    new_entries_local.append(entry)

        # Deduplicate by URL — keep highest-confidence entry per URL
        seen: dict[str, dict] = {}
        for entry in all_results:
            url = entry["url"]
            if url not in seen or entry["confidence"] > seen[url]["confidence"]:
                seen[url] = entry
        top = sorted(seen.values(), key=lambda x: x["confidence"], reverse=True)[:5]
        #print(f"[SCRAPE] Top {len(top)} unique result(s) for tool message  ({len(new_entries_local)} added to history)")
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

    Builds its own minimal context instead of reusing state["messages"], so the
    model never sees the unresolved tool_calls from the plan message, which
    would cause an API validation error.
    """
    stable = (
        f"Universal agent instructions:\n{state.get('context', '')}\n\n"
        f"Node instructions:\n{scrape_prompt}"
    )
    volatile = "\n\nRuntime context:\n" + json.dumps(
        {
            "latest_user_message": latest_human_message_content(state),
            "current_year": state.get("current_year"),
            "topic": topic,
            "scrape_history": state.get("scrape_history", [])[-20:],
        },
        indent=2,
    )
    stable_block: dict = {"type": "text", "text": stable}
    if NODE_PROVIDERS.get("scrape") == "anthropic":
        stable_block["cache_control"] = {"type": "ephemeral"}
    system_blocks = [stable_block, {"type": "text", "text": volatile}]
    model = get_node_model("scrape").with_structured_output(ScrapeDecision)
    return await model.ainvoke([SystemMessage(content=system_blocks)])
