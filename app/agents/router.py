"""Query routing — decides whether a message needs a tool (weather/crypto/
search) or goes straight to Gemini. Ported from handle_query() in
gemini_retrieval.py; still keyword-based for Phase 1 (Rules.md/Architecture.md
flag upgrading this to real intent classification as a later-phase task —
don't jump ahead of it).
"""

import re
from typing import Dict, Generator, List

from app.ai.gemini_client import call_gemini, stream_gemini
from app.memory.session_memory import recent_context
from app.tools.crypto import get_crypto_price
from app.tools.search import google_search
from app.tools.weather import get_weather

_WEATHER_RE = re.compile(r"\bweather\b.*\bin\s+([a-zA-Z\s]+)", re.IGNORECASE)
_CRYPTO_RE = re.compile(r"\b(price of|cost of)\s+([a-zA-Z]+)", re.IGNORECASE)
_SEARCH_RE = re.compile(r"\bsearch(?: for)?\s+(.+)", re.IGNORECASE)
_IMAGE_RE = re.compile(r"\bimage(?:s)? of\s+(.+)", re.IGNORECASE)


def _extract_city(text: str, default: str = "your area") -> str:
    match = _WEATHER_RE.search(text)
    return match.group(1).strip() if match else default


def route_query(user_input: str, history: List[Dict]) -> str:
    """Non-streaming route — used for tool-backed answers where there's no
    meaningful token-by-token output (weather/crypto/search results)."""
    text = user_input.strip()

    if _WEATHER_RE.search(text):
        city = _extract_city(text)
        return get_weather(city)

    crypto_match = _CRYPTO_RE.search(text)
    if crypto_match:
        coin = crypto_match.group(2)
        result = get_crypto_price(coin)
        return result or f"Sorry, I couldn't find a price for '{coin}'."

    image_match = _IMAGE_RE.search(text)
    if image_match:
        results = google_search(image_match.group(1), search_type="image")
        if not results:
            return "No image results found (or search isn't configured)."
        return "\n".join(f"- {r['title']}: {r['link']}" for r in results)

    search_match = _SEARCH_RE.search(text)
    if search_match:
        results = google_search(search_match.group(1))
        if not results:
            return "No search results found (or search isn't configured)."
        return "\n".join(f"- {r['title']}: {r['link']}\n  {r['snippet']}" for r in results)

    return ""  # signals "not a tool query" — caller falls through to Gemini


def stream_route_query(user_input: str, history: List[Dict]) -> Generator[str, None, None]:
    """Streaming entry point used by the /api/chat SSE route. Tool answers are
    yielded as one chunk (they're already complete); Gemini answers stream
    token by token."""
    tool_answer = route_query(user_input, history)
    if tool_answer:
        yield tool_answer
        return

    context = recent_context(history)
    prompt = (
        f"You are Nimbus, a helpful, concise AI assistant.\n\n"
        f"Conversation so far:\n{context}\n\n"
        f"User: {user_input}\nNimbus:"
    )
    yield from stream_gemini(prompt)
