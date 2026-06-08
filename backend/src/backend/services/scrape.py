"""Lightweight search-and-scrape helpers for agent web research."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import httpx
from ddgs import DDGS
from scrapy import Selector

logger = logging.getLogger(__name__)

_SNIPPET_LENGTH = 600
_TIMEOUT = 8.0
_MIN_CONFIDENCE = 0.25
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

_SOURCE_TYPE_PATTERNS: dict[str, list[str]] = {
    "SEC filing":            ["sec.gov", "edgar"],
    "earnings press release":["businesswire.com", "prnewswire.com", "globenewswire.com"],
    "analyst report":        ["seekingalpha.com", "morningstar.com", "finviz.com"],
    "news article":          ["bloomberg.com", "reuters.com", "ft.com", "wsj.com", "cnbc.com", "marketwatch.com"],
    "investor relations":    ["/investor", "ir.", "investors."],
}


@dataclass
class ScrapeResult:
    """Normalized web research result returned to the agent tool layer."""

    url: str
    title: str
    snippet: str
    confidence: float
    source_type: str = ""


async def search_and_scrape_async(
    query: str,
    max_results: int = 3,
    *,
    avoid: list[str] | None = None,
    research_goal: str = "",
    preferred_source_types: list[str] | None = None,
) -> list[ScrapeResult]:
    """Search DuckDuckGo and scrape top results asynchronously.

    Args:
        query: Search query string.
        max_results: Number of pages to fetch and scrape.
        avoid: URL or title substrings to exclude from results.
        research_goal: One-sentence description of what to find — used to
            improve confidence scoring.
        preferred_source_types: Source categories that get a confidence bonus
            when matched (e.g. "SEC filing", "news article").
    """
    avoid_lower = [a.lower() for a in (avoid or [])]
    preferred_lower = [p.lower() for p in (preferred_source_types or [])]

    print(f"[SCRAPE] search_and_scrape_async: {query!r}  max_results={max_results}")
    fetch_count = max_results + len(avoid_lower) + 2
    try:
        # DDGS is synchronous — run in a thread to avoid blocking the event loop
        raw_hits = await asyncio.to_thread(
            lambda: list(DDGS().text(query, max_results=fetch_count))
        )
    except Exception as exc:
        logger.warning("DuckDuckGo search failed for %r: %s", query, exc)
        print(f"[SCRAPE] DuckDuckGo FAILED: {exc}")
        return []

    print(f"[SCRAPE] DuckDuckGo returned {len(raw_hits)} raw hit(s)")

    if avoid_lower:
        raw_hits = [
            h for h in raw_hits
            if not any(
                a in h.get("href", "").lower() or a in h.get("title", "").lower()
                for a in avoid_lower
            )
        ]

    hits = [h for h in raw_hits if h.get("href")][:max_results]

    async with httpx.AsyncClient(
        headers={"User-Agent": _USER_AGENT},
        follow_redirects=True,
        timeout=_TIMEOUT,
    ) as client:
        tasks = [
            _fetch_and_parse(
                client,
                h["href"],
                h.get("title", ""),
                query,
                research_goal,
                h.get("body", ""),
            )
            for h in hits
        ]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    results: list[ScrapeResult] = []
    for r in raw_results:
        if not isinstance(r, ScrapeResult):
            continue
        if r.confidence < _MIN_CONFIDENCE:
            continue
        r.source_type = _infer_source_type(r.url)
        if preferred_lower and any(p in r.source_type.lower() for p in preferred_lower):
            r.confidence = min(1.0, round(r.confidence + 0.1, 3))
            print(f"[SCRAPE]   preferred source bonus applied → {r.confidence}  ({r.source_type})")
        results.append(r)

    print(f"[SCRAPE] {len(results)} result(s) above confidence threshold {_MIN_CONFIDENCE}")
    return sorted(results, key=lambda r: r.confidence, reverse=True)


def search_and_scrape(query: str, max_results: int = 3) -> list[ScrapeResult]:
    """Synchronous wrapper kept for backwards compatibility."""
    return asyncio.run(search_and_scrape_async(query, max_results))


async def _fetch_and_parse(
    client: httpx.AsyncClient,
    url: str,
    title: str,
    query: str,
    research_goal: str,
    fallback_snippet: str,
) -> ScrapeResult | None:
    """Fetch one search result and reduce the page to a scored text snippet."""
    print(f"[SCRAPE] Fetching: {url[:80]}")
    try:
        response = await client.get(url)
        response.raise_for_status()
        html = response.text

        sel = Selector(text=html)

        # Prefer semantically scoped content areas over all <p> tags
        text = " ".join(sel.css("main p::text, article p::text, section p::text").getall())
        if not text:
            text = " ".join(sel.css("p::text").getall())
        text = " ".join(text.split())

        if not text:
            print(f"[SCRAPE]   No body text found, using DDG snippet fallback")
            text = fallback_snippet
        else:
            print(f"[SCRAPE]   Scraped {len(text)} chars of body text")

    except Exception as exc:
        logger.debug("Failed to fetch %s: %s", url, exc)
        print(f"[SCRAPE]   Fetch failed ({exc.__class__.__name__}): {exc}")
        if not fallback_snippet:
            return None
        text = fallback_snippet

    snippet = text[:_SNIPPET_LENGTH]
    confidence = _confidence(text, query, research_goal)
    print(f"[SCRAPE]   confidence={confidence:.3f}  title={title[:50]!r}")
    return ScrapeResult(url=url, title=title, snippet=snippet, confidence=confidence)


def _confidence(text: str, query: str, research_goal: str = "") -> float:
    """Score whether scraped text appears relevant to the query and research goal."""
    if not text:
        return 0.0

    text_lower = text.lower()

    query_words = {w.lower() for w in query.split() if len(w) > 2}
    query_score = (
        sum(1 for w in query_words if w in text_lower) / len(query_words)
        if query_words else 0.5
    )

    length_score = min(len(text) / 2000, 1.0)

    if research_goal:
        goal_words = {w.lower() for w in research_goal.split() if len(w) > 3}
        goal_score = (
            sum(1 for w in goal_words if w in text_lower) / len(goal_words)
            if goal_words else 0.0
        )
        return round(0.45 * query_score + 0.35 * goal_score + 0.20 * length_score, 3)

    return round(0.60 * query_score + 0.40 * length_score, 3)


def _infer_source_type(url: str) -> str:
    """Classify a URL into the coarse source categories used by the agent."""
    url_lower = url.lower()
    for source_type, patterns in _SOURCE_TYPE_PATTERNS.items():
        if any(p in url_lower for p in patterns):
            return source_type
    return "web"
