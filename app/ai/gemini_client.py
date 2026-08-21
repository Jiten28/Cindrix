"""Gemini API client (google-genai SDK).

An optional model override (for the selector UI) is validated against
settings.GEMINI_MODEL_IDS, so an unexpected string can't reach the API as a model
name and a Groq id resolves to GEMINI_MODEL on the fallback leg."""

import json
import re
from typing import Generator, Optional

from google import genai
from google.genai import types

from app.config import settings

_client: Optional[genai.Client] = None
# Only Gemini-provider ids are valid overrides here; a Groq id reaching this
# module (as retry.py's fallback leg) must resolve to GEMINI_MODEL, not be forwarded.
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
    """Non-streaming call returning one complete answer."""
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
    """Streaming call — yields text chunks as Gemini generates them."""
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
    Uses the same GOOGLE_API_KEY as chat — no separate Custom Search API needed."""
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
    """Streaming call with an image attached. Also covers OCR — Gemini reads
    text embedded in images natively, so no separate OCR library."""
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
