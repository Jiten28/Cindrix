"""Gemini API client.

Rebuilt on the google-genai SDK (the google-generativeai package this
originally used, and the gemini-1.5-flash model it called, were both fully
deprecated/shut down by Google — see the 404 error you hit). Function names
and behavior are unchanged so nothing calling this module needs to change.
"""

import json
import re
from typing import Generator, Optional

from google import genai
from google.genai import types

from app.config import settings

_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.GOOGLE_API_KEY)
    return _client


def call_gemini(prompt: str) -> str:
    """Non-streaming call — used by tools that need a single complete answer
    (e.g. the Gemini weather fallback, JSON-mode calls)."""
    if not settings.GOOGLE_API_KEY:
        return "Gemini is not configured (missing GOOGLE_API_KEY)."
    try:
        resp = _get_client().models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
        )
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
        stream = _get_client().models.generate_content_stream(
            model=settings.GEMINI_MODEL,
            contents=prompt,
        )
        for chunk in stream:
            if chunk.text:
                yield chunk.text
    except Exception as e:
        yield f"(Gemini error: {e})"
