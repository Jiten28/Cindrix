"""Web and image search via Tavily."""

import logging
from typing import List, Optional

import requests

from app.config import settings

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://api.tavily.com/search"
_MAX_LOGGED_BODY_CHARS = 500  # error bodies can be long; the first lines carry the reason


def _tavily_request(query: str, num: int, include_images: bool) -> Optional[dict]:
    if not settings.TAVILY_API_KEY:
        logger.warning("[search] TAVILY_API_KEY not set — search is unavailable")
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
        body = e.response.text[:_MAX_LOGGED_BODY_CHARS] if e.response is not None else "(no body)"
        logger.error("[search] HTTP error: %s | response body: %s", e, body)
        return None
    except Exception as e:
        logger.error("[search] request failed: %s", e)
        return None


def web_search(query: str, num: int = 5) -> List[dict]:
    """List of {title, link, snippet} dicts; empty on failure."""
    js = _tavily_request(query, num, include_images=False)
    if js is None:
        return []
    results = js.get("results", [])
    if not results:
        logger.info("[search] query succeeded but returned 0 results for: %r", query)
    return [
        {"title": r.get("title", ""), "link": r.get("url", ""), "snippet": r.get("content", "")}
        for r in results
    ]


def image_search(query: str, num: int = 5) -> List[dict]:
    """List of {title, link, snippet} dicts (snippet always empty); empty on failure."""
    js = _tavily_request(query, num, include_images=True)
    if js is None:
        return []
    images = js.get("images", [])
    if not images:
        logger.info("[search] image query succeeded but returned 0 images for: %r", query)
    return [
        {"title": img.get("description", "") or query, "link": img.get("url", ""), "snippet": ""}
        for img in images
    ]
