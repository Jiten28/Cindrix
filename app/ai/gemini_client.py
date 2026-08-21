"""Gemini API client.

Rebuilt on the google-genai SDK (the google-generativeai package this
originally used, and the gemini-1.5-flash model it called, were both fully
deprecated/shut down by Google — see the 404 error that confirmed this).
Function names and behavior are unchanged so nothing calling this module
needs to change.

Phase 4: call_gemini/stream_gemini accept an optional model override (for
the model selector UI) — validated against settings.GEMINI_MODEL_IDS (the
Gemini-provider ids only, NOT the full AVAILABLE_MODELS list) rather than
passed straight through. So an unexpected string from the client can't reach
the API as a model name, AND a Groq id selected in the UI (which reaches this
module only as the Gemini *fallback* leg of app/ai/retry.py) resolves to
GEMINI_MODEL here instead of being sent to Gemini verbatim.
"""

import json
import re
from typing import Generator, Optional

from google import genai
from google.genai import types

from app.config import settings

_client: Optional[genai.Client] = None
# Only the Gemini-provider ids are valid model overrides here — a Groq id
# from the selector reaches this module only as retry.py's Gemini fallback,
# and must resolve to GEMINI_MODEL, not be forwarded to the Gemini API.
_VALID_MODEL_IDS = settings.GEMINI_MODEL_IDS


def _resolve_model(model: Optional[str]) -> str:
    if model and model in _VALID_MODEL_IDS:
        return model
    return settings.GEMINI_MODEL


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.GOOGLE_API_KEY)
    return _client


def call_gemini(prompt: str, model: Optional[str] = None) -> str:
    """Non-streaming call — used by tools that need a single complete answer
    (e.g. the Gemini weather fallback, JSON-mode calls)."""
    if not settings.GOOGLE_API_KEY:
        return "Gemini is not configured (missing GOOGLE_API_KEY)."
    try:
        resp = _get_client().models.generate_content(
            model=_resolve_model(model),
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


def stream_gemini(prompt: str, model: Optional[str] = None) -> Generator[str, None, None]:
    """Streaming call — yields text chunks as Gemini generates them.
    Used by app/api/routes.py for the chat-turn SSE response."""
    if not settings.GOOGLE_API_KEY:
        yield "Gemini is not configured (missing GOOGLE_API_KEY)."
        return
    try:
        stream = _get_client().models.generate_content_stream(
            model=_resolve_model(model),
            contents=prompt,
        )
        for chunk in stream:
            if chunk.text:
                yield chunk.text
    except Exception as e:
        yield f"(Gemini error: {e})"


def stream_gemini_search(prompt: str, model: Optional[str] = None) -> Generator[str, None, None]:
    """Streaming call using Gemini's built-in Google Search grounding tool.

    Replaces the old Custom Search JSON API path for general web search —
    that API closed to new signups in 2025 and fully sunsets January 1,
    2027 (see Memory.md). This uses the same GOOGLE_API_KEY already
    configured for chat; no separate Custom Search API / CSE ID needed.
    """
    if not settings.GOOGLE_API_KEY:
        yield "Gemini is not configured (missing GOOGLE_API_KEY)."
        return
    try:
        grounding_tool = types.Tool(google_search=types.GoogleSearch())
        config = types.GenerateContentConfig(tools=[grounding_tool])
        stream = _get_client().models.generate_content_stream(
            model=_resolve_model(model),
            contents=prompt,
            config=config,
        )
        for chunk in stream:
            if chunk.text:
                yield chunk.text
    except Exception as e:
        yield f"(Gemini error: {e})"


def stream_gemini_vision(prompt: str, image_bytes: bytes, mime_type: str, model: Optional[str] = None) -> Generator[str, None, None]:
    """Streaming call with an image attached — used for image understanding
    (Phase 2). Also covers the OCR use case: Gemini reads text embedded in
    images natively, so a scanned document just works here without a
    separate OCR library."""
    if not settings.GOOGLE_API_KEY:
        yield "Gemini is not configured (missing GOOGLE_API_KEY)."
        return
    try:
        image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        stream = _get_client().models.generate_content_stream(
            model=_resolve_model(model),
            contents=[image_part, prompt],
        )
        for chunk in stream:
            if chunk.text:
                yield chunk.text
    except Exception as e:
        yield f"(Gemini error: {e})"
