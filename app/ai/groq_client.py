"""Groq API client — OpenAI-compatible chat completions over `requests` (no extra
SDK for a single REST endpoint).

    POST https://api.groq.com/openai/v1/chat/completions
    Authorization: Bearer <GROQ_API_KEY>
    SSE stream of chat.completion.chunk lines, terminated by "data: [DONE]".

Default model is `openai/gpt-oss-120b` (Groq deprecated llama-3.3-70b-versatile).
Never raises; yields "(Groq error: ...)" on failure so retry.py's error detection
works identically for both providers."""

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
    """Non-streaming call returning the full response as one string."""
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
    """Streaming call — yields text chunks as Groq generates them."""
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
            # Groq's error bodies are JSON with a useful message — log it.
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
