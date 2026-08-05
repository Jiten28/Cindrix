"""Web and image search via Tavily.

Second revision of this file. General web search briefly used Gemini's
built-in Google Search grounding tool — reverted because that tool
effectively requires a *billed* Google Cloud project to get meaningful
quota; on a plain free-tier API key it 429s almost immediately
(RESOURCE_EXHAUSTED) while normal (non-grounded) generation keeps working
fine, since only grounding is gated this way. That distinction wasn't
caught before shipping it — see Memory.md's Post-Launch Fixes. Both general
and image search now go through Tavily, which was already in use for image
search and confirmed working on its free tier (1,000 credits/month, no
card).

Originally, before that, this was Google Custom Search JSON API — replaced
because Google closed that API to new customers in 2025 and shuts it down
entirely January 1, 2027.
"""

from typing import List, Optional

import requests

from app.config import settings

_SEARCH_URL = "https://api.tavily.com/search"


def _tavily_request(query: str, num: int, include_images: bool) -> Optional[dict]:
    if not settings.TAVILY_API_KEY:
        print("[search] TAVILY_API_KEY not set")
        return None
    try:
        payload = {
            "query": query,
            "max_results": num,
            "search_depth": "basic",
        }
        if include_images:
            payload["include_images"] = True
            payload["include_image_descriptions"] = True
        headers = {
            "Authorization": f"Bearer {settings.TAVILY_API_KEY}",
            "Content-Type": "application/json",
        }
        r = requests.post(_SEARCH_URL, json=payload, headers=headers, timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.HTTPError as e:
        body = e.response.text if e.response else "(no body)"
        print(f"[search] HTTP error: {e}\nResponse body: {body}")
        return None
    except Exception as e:
        print(f"[search] unexpected error: {e}")
        return None


def web_search(query: str, num: int = 5) -> List[dict]:
    """Returns a list of {title, link, snippet} dicts, empty list on
    failure. The real failure reason is printed to the server console
    either way."""
    js = _tavily_request(query, num, include_images=False)
    if js is None:
        return []
    results = js.get("results", [])
    if not results:
        print(f"[search] query succeeded but returned 0 results for: {query!r}")
    return [
        {"title": r.get("title", ""), "link": r.get("url", ""), "snippet": r.get("content", "")}
        for r in results
    ]


def image_search(query: str, num: int = 5) -> List[dict]:
    """Returns a list of {title, link, snippet} dicts (snippet always empty
    for images), empty list on failure."""
    js = _tavily_request(query, num, include_images=True)
    if js is None:
        return []
    images = js.get("images", [])
    if not images:
        print(f"[search] image query succeeded but returned 0 images for: {query!r}")
    return [
        {"title": img.get("description", "") or query, "link": img.get("url", ""), "snippet": ""}
        for img in images
    ]
