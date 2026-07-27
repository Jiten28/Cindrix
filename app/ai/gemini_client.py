"""Gemini API client.

call_gemini() and call_gemini_json() are ported directly from
gemini_retrieval.py. stream_gemini() is new for Phase 1 — it's what lets the
Flask route in app/api/routes.py send tokens to the browser as they arrive
instead of waiting for the full response.
"""

import json
import re
from typing import Generator, Optional

import google.generativeai as genai

from app.config import settings

if settings.GOOGLE_API_KEY:
    genai.configure(api_key=settings.GOOGLE_API_KEY)


def _get_model() -> genai.GenerativeModel:
    return genai.GenerativeModel(settings.GEMINI_MODEL)


def call_gemini(prompt: str) -> str:
    """Non-streaming call — used by tools that need a single complete answer
    (e.g. the Gemini weather fallback, JSON-mode calls)."""
    if not settings.GOOGLE_API_KEY:
        return "Gemini is not configured (missing GOOGLE_API_KEY)."
    try:
        resp = _get_model().generate_content(prompt)
        return (resp.text or "").strip() if resp else "No response."
    except Exception as e:
        return f"(Gemini error: {e})"


def call_gemini_json(prompt: str) -> Optional[dict]:
    """Ask Gemini to respond with a single JSON object. Returns dict or None."""
    text = call_gemini(prompt)
    try:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except Exception:
        return None
    return None


def stream_gemini(prompt: str) -> Generator[str, None, None]:
    """Streaming call — yields text chunks as Gemini generates them.
    Used by app/api/routes.py for the chat-turn SSE response."""
    if not settings.GOOGLE_API_KEY:
        yield "Gemini is not configured (missing GOOGLE_API_KEY)."
        return
    try:
        response = _get_model().generate_content(prompt, stream=True)
        for chunk in response:
            if chunk.text:
                yield chunk.text
    except Exception as e:
        yield f"(Gemini error: {e})"
