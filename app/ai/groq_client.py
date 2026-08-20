"""Groq API client — OpenAI-compatible chat completions, via `requests`
rather than the `openai`/`groq` SDK packages, to avoid adding a new
dependency for what's a single REST endpoint (matches the pattern already
used for Sarvam in app/ai/stt.py).

Endpoint/auth/streaming details confirmed directly against Groq's live
docs and changelog while building this, not recalled from training data:
    POST https://api.groq.com/openai/v1/chat/completions
    header: Authorization: Bearer <GROQ_API_KEY>
    body: {"model": ..., "messages": [...], "stream": true}
    SSE response: "data: {...}" lines, each a chat.completion.chunk with
    choices[0].delta.content, terminated by a literal "data: [DONE]" line
    — standard OpenAI-compatible streaming format.

Model default is `openai/gpt-oss-120b`, NOT `llama-3.3-70b-versatile` (the
model this project was originally going to default to) — Groq deprecated
that model (announced June 17, 2026, confirmed via their own live
"Model Deprecation" docs page and changelog while building this) with a
shutdown date of August 16, 2026, already past by the time this was
written. `openai/gpt-oss-120b` is Groq's own recommended replacement and
their current flagship production (not preview) open-weight model. Same
class of lesson this project already logged once for Gemini
(`gemini-1.5-flash` deprecation) — verify current model IDs against live
docs, don't trust an example snippet's specific model name.

Mirrors app/ai/gemini_client.py's error-handling shape on purpose: never
raises, yields "(Groq error: ...)" on failure so app/ai/retry.py's
_is_error_chunk()/_looks_transient() detection (built for that exact
shape already) works identically for both providers without needing
provider-specific error parsing in the retry layer.
"""

import json
import logging
from typing import Generator, Optional

import requests

from app.config import settings

logger = logging.getLogger(__name__)

_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
_CONNECT_TIMEOUT = 10
_READ_TIMEOUT = 30


def call_groq(prompt: str, model: Optional[str] = None) -> str:
    """Non-streaming call — returns the complete response as a single
    string. Used as the primary generation provider for non-streaming
    generation calls (e.g. app/tools/weather.py's Gemini-fallback
    description) — see app/ai/retry.py's call_generation(). Mirrors
    app/ai/gemini_client.py's call_gemini() shape/error-sentinel
    convention for the same reason stream_groq() mirrors stream_gemini()
    — see this module's docstring."""
    if not settings.GROQ_API_KEY:
        return "(Groq error: not configured — missing GROQ_API_KEY)"

    resolved_model = model or settings.GROQ_MODEL
    try:
        response = requests.post(
            _ENDPOINT,
            headers={
                "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": resolved_model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
            timeout=(_CONNECT_TIMEOUT, _READ_TIMEOUT),
        )
        if response.status_code != 200:
            body = response.text[:500]
            logger.error("[groq] HTTP %s: %s", response.status_code, body)
            return f"(Groq error: {response.status_code} {body})"
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            return "(Groq error: empty response — no choices returned)"
        return (choices[0].get("message", {}).get("content") or "").strip()
    except requests.exceptions.Timeout:
        logger.error("[groq] request timed out")
        return "(Groq error: timeout)"
    except requests.exceptions.RequestException as e:
        logger.error("[groq] request failed: %s", e)
        return f"(Groq error: {e})"


def stream_groq(prompt: str, model: Optional[str] = None) -> Generator[str, None, None]:
    """Streaming call — yields text chunks as Groq generates them. Used as
    the primary generation provider for RAG-serving calls — see
    app/ai/retry.py's stream_generation()."""
    if not settings.GROQ_API_KEY:
        yield "(Groq error: not configured — missing GROQ_API_KEY)"
        return

    resolved_model = model or settings.GROQ_MODEL
    try:
        response = requests.post(
            _ENDPOINT,
            headers={
                "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": resolved_model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": True,
            },
            stream=True,
            timeout=(_CONNECT_TIMEOUT, _READ_TIMEOUT),
        )
        if response.status_code != 200:
            # Read the body before raising our own error — Groq's error
            # responses are JSON with a useful message field, worth
            # logging even though the user only sees the generic retry-
            # layer message.
            body = response.text[:500]
            logger.error("[groq] HTTP %s: %s", response.status_code, body)
            yield f"(Groq error: {response.status_code} {body})"
            return

        for line in response.iter_lines(decode_unicode=False):
            if not line:
                continue
            line = line.decode("utf-8")
            if not line.startswith("data: "):
                continue
            payload = line[len("data: "):]
            if payload.strip() == "[DONE]":
                break
            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                continue
            choices = event.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            text = delta.get("content")
            if text:
                yield text

    except requests.exceptions.Timeout:
        logger.error("[groq] request timed out")
        yield "(Groq error: timeout)"
    except requests.exceptions.RequestException as e:
        logger.error("[groq] request failed: %s", e)
        yield f"(Groq error: {e})"
