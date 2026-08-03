"""Image search via Tavily.

General web search moved entirely to Gemini's built-in Google Search
grounding tool (see app/ai/gemini_client.py's stream_gemini_search) — no
separate API needed for that anymore. This file now only handles the
narrower "image of X" pattern, since Gemini's grounding tool answers with
text + citations, not a list of direct image URLs.

Originally built on Google Custom Search JSON API — replaced because Google
closed that API to new customers in 2025 and shuts it down entirely on
January 1, 2027 (see Memory.md). Tavily was picked for this narrower need
because it's free (1,000 credits/month, no card required) and its
`include_images` option returns exactly the {url, description} shape this
needs.
"""

from typing import List, Optional

import requests

from app.config import settings

_SEARCH_URL = "https://api.tavily.com/search"


def image_search(query: str, num: int = 5) -> List[dict]:
    """Returns a list of {title, link, snippet} dicts (snippet always empty
    for images), empty list on failure. The real failure reason is printed
    to the server console either way — "configured but still failing"
    shouldn't be a silent dead end."""
    if not settings.TAVILY_API_KEY:
        print("[search] TAVILY_API_KEY not set")
        return []
    try:
        payload = {
            "query": query,
            "max_results": num,
            "search_depth": "basic",
            "include_images": True,
            "include_image_descriptions": True,
        }
        headers = {
            "Authorization": f"Bearer {settings.TAVILY_API_KEY}",
            "Content-Type": "application/json",
        }
        r = requests.post(_SEARCH_URL, json=payload, headers=headers, timeout=10)
        r.raise_for_status()
        js = r.json()
        images = js.get("images", [])
        if not images:
            print(f"[search] image query succeeded but returned 0 images for: {query!r}")
        return [
            {"title": img.get("description", "") or query, "link": img.get("url", ""), "snippet": ""}
            for img in images
        ]
    except requests.exceptions.HTTPError as e:
        body = e.response.text if e.response else "(no body)"
        print(f"[search] HTTP error: {e}\nResponse body: {body}")
        return []
    except Exception as e:
        print(f"[search] unexpected error: {e}")
        return []
