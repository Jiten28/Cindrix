"""Query routing — decides whether a message needs a tool (weather/crypto/
search), an active attachment (RAG/vision), or a plain conversational answer.
Ported from handle_query() in gemini_retrieval.py; still keyword-based for
Phase 1 (Rules.md/Architecture.md flag upgrading this to real intent
classification as a later-phase task — don't jump ahead of it).

Phase 3 added detect_tool() as a single source of truth for "which path will
this message take" — used both to actually answer it and to label the
analytics event. Phase 4 threads user_id through (conversations and
attachments are now per-user) and an optional model override (model
selector UI).
"""

import re
from typing import Dict, Generator, List, Optional

from app.ai.embeddings import top_k_chunks
from app.ai.gemini_client import call_gemini, stream_gemini, stream_gemini_search, stream_gemini_vision
from app.memory.attachment_store import get_active
from app.memory.conversation_store import recent_context
from app.tools.crypto import get_crypto_price
from app.tools.search import image_search
from app.tools.weather import get_weather

_WEATHER_RE = re.compile(r"\bweather\b.*\bin\s+([a-zA-Z\s]+)", re.IGNORECASE)
_CRYPTO_RE = re.compile(r"\b(price of|cost of)\s+([a-zA-Z]+)", re.IGNORECASE)
_SEARCH_RE = re.compile(r"\bsearch(?: for)?\s+(.+)", re.IGNORECASE)
_IMAGE_RE = re.compile(r"\bimage(?:s)? of\s+(.+)", re.IGNORECASE)


def _extract_city(text: str, default: str = "your area") -> str:
    match = _WEATHER_RE.search(text)
    return match.group(1).strip() if match else default


def detect_tool(user_input: str, attachment: Optional[Dict] = None) -> str:
    """Pure classification, no side effects — mirrors the checks in
    route_query()/stream_route_query() exactly, so analytics logging always
    matches what actually answered the message."""
    text = user_input.strip()
    if _WEATHER_RE.search(text):
        return "weather"
    if _CRYPTO_RE.search(text):
        return "crypto"
    if _IMAGE_RE.search(text):
        return "image_search"
    if _SEARCH_RE.search(text):
        return "web_search"
    if attachment:
        if attachment["kind"] == "image":
            return "image_vision"
        if attachment["kind"] == "document":
            return "document_rag"
    return "general"


def route_query(user_input: str, history: List[Dict]) -> str:
    """Non-streaming route — used for tool-backed answers where there's no
    meaningful token-by-token output (weather/crypto/image-search results).
    General web search is NOT handled here — it needs Gemini's streaming
    Google Search grounding tool now (see stream_route_query), not the old
    Custom Search JSON API path."""
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
        results = image_search(image_match.group(1))
        if not results:
            return "No image results found (or image search isn't configured — see .env.example)."
        return "\n".join(f"- {r['title']}: {r['link']}" for r in results)

    return ""  # signals "not a tool query" — caller falls through to Gemini/search


def stream_route_query(
    user_input: str,
    user_id: str,
    conversation_id: str,
    model: Optional[str] = None,
    user_display_name: Optional[str] = None,
) -> Generator[str, None, None]:
    """Streaming entry point used by the /api/chat SSE route. Tool answers are
    yielded as one chunk (they're already complete); Gemini answers stream
    token by token.

    Priority order: explicit tool intent (weather/crypto/search) first, then
    an active attachment (uploaded document → RAG, uploaded image → vision),
    then a plain conversational answer. An uploaded file doesn't hijack every
    message — "what's the weather" still checks the weather even with a
    document attached — but once tool intent is ruled out, the attachment
    gets first shot at answering before falling back to plain chat.
    """
    tool_answer = route_query(user_input, [])
    if tool_answer:
        yield tool_answer
        return

    search_match = _SEARCH_RE.search(user_input.strip())
    if search_match:
        yield from stream_gemini_search(search_match.group(1), model=model)
        return

    attachment = get_active(f"{user_id}:{conversation_id}")
    name_context = f" The user's name is {user_display_name}." if user_display_name else ""

    if attachment:
        if attachment["kind"] == "image":
            with open(attachment["filepath"], "rb") as f:
                image_bytes = f.read()
            yield from stream_gemini_vision(user_input, image_bytes, attachment["mime_type"], model=model)
            return

        if attachment["kind"] == "document":
            relevant_chunks = top_k_chunks(
                user_input, attachment["chunks"], attachment["embeddings"], k=4
            )
            context_block = "\n\n---\n\n".join(relevant_chunks)
            prompt = (
                f"You are Nimbus, a helpful, concise AI assistant.{name_context} "
                f"The user has uploaded a document called '{attachment['filename']}'. Use the "
                f"following excerpts from it to answer their question. If the "
                f"excerpts don't contain the answer, say so rather than guessing.\n\n"
                f"Document excerpts:\n{context_block}\n\n"
                f"User question: {user_input}\nNimbus:"
            )
            yield from stream_gemini(prompt, model=model)
            return

    context = recent_context(user_id, conversation_id)
    prompt = (
        f"You are Nimbus, a helpful, concise AI assistant.{name_context}\n\n"
        f"Conversation so far:\n{context}\n\n"
        f"User: {user_input}\nNimbus:"
    )
    yield from stream_gemini(prompt, model=model)
