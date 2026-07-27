"""Web & image search via Google Custom Search. Ported from gemini_retrieval.py."""

from typing import List, Optional

import requests

from app.config import settings


def google_search(query: str, search_type: Optional[str] = None, num: int = 5) -> List[dict]:
    """search_type=None -> web results, search_type='image' -> image results.
    Returns a list of {title, link, snippet} dicts, empty list on failure."""
    if not settings.GOOGLE_API_KEY or not settings.GOOGLE_CSE_ID:
        return []
    try:
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "key": settings.GOOGLE_API_KEY,
            "cx": settings.GOOGLE_CSE_ID,
            "q": query,
            "num": num,
            "gl": settings.GOOGLE_API_LOCATION,
        }
        if search_type == "image":
            params["searchType"] = "image"
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        js = r.json()
        items = js.get("items", [])
        return [
            {
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "snippet": item.get("snippet", ""),
            }
            for item in items
        ]
    except Exception:
        return []
