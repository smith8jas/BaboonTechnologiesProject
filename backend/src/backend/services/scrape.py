from __future__ import annotations

import logging
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)

_SNIPPET_LENGTH = 500
_TIMEOUT = 8
_MIN_CONFIDENCE = 0.25


@dataclass
class ScrapeResult:
    url: str
    title: str
    snippet: str
    confidence: float


def search_and_scrape(query: str, max_results: int = 3) -> list[ScrapeResult]:
    """Search DuckDuckGo and scrape the top results for a given query."""
    print(f"[SCRAPE] search_and_scrape: {query!r}  max_results={max_results}")
    try:
        hits = list(DDGS().text(query, max_results=max_results))
    except Exception as exc:
        logger.warning("DuckDuckGo search failed for %r: %s", query, exc)
        print(f"[SCRAPE] DuckDuckGo FAILED: {exc}")
        return []

    print(f"[SCRAPE] DuckDuckGo returned {len(hits)} raw hit(s)")
    results = []
    for hit in hits:
        url = hit.get("href", "")
        title = hit.get("title", "")
        ddg_body = hit.get("body", "")
        if not url:
            continue
        result = _fetch_and_parse(url, title, query, fallback_snippet=ddg_body)
        if result and result.confidence >= _MIN_CONFIDENCE:
            results.append(result)

    print(f"[SCRAPE] {len(results)} result(s) above confidence threshold {_MIN_CONFIDENCE}")
    return sorted(results, key=lambda r: r.confidence, reverse=True)


def _fetch_and_parse(
    url: str,
    title: str,
    query: str,
    fallback_snippet: str = "",
) -> ScrapeResult | None:
    print(f"[SCRAPE] Fetching: {url[:80]}")
    try:
        response = requests.get(
            url,
            timeout=_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = " ".join(
            p.get_text(separator=" ", strip=True)
            for p in soup.find_all("p")
        )
        text = " ".join(text.split())
        if not text:
            print(f"[SCRAPE]   No <p> text found, using DDG snippet fallback")
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
    confidence = _confidence(text, query)
    print(f"[SCRAPE]   confidence={round(confidence, 3):.3f}  title={title[:50]!r}")
    return ScrapeResult(url=url, title=title, snippet=snippet, confidence=round(confidence, 3))


def _confidence(text: str, query: str) -> float:
    if not text:
        return 0.0
    words = {w.lower() for w in query.split() if len(w) > 2}
    text_lower = text.lower()
    keyword_score = sum(1 for w in words if w in text_lower) / len(words) if words else 0.5
    length_score = min(len(text) / 2000, 1.0)
    return 0.6 * keyword_score + 0.4 * length_score
