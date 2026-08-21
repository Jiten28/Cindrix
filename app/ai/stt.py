"""Sarvam AI speech-to-text client.

    POST https://api.sarvam.ai/speech-to-text
    header: api-subscription-key: <key>
    multipart form: file=<audio>, model, language_code
    200: {"transcript", "language_code", ...}; errors: {"error": {...}}

The browser Web Speech API stays as the keyless dev fallback; STT_PROVIDER switches.
"""

import logging
from typing import Optional, TypedDict

import requests

from app.config import settings

logger = logging.getLogger(__name__)

_ENDPOINT = "https://api.sarvam.ai/speech-to-text"
_TIMEOUT_SECONDS = 25  # REST endpoint is documented for audio under 30s


class TranscriptionResult(TypedDict):
    ok: bool
    transcript: str
    language_code: Optional[str]
    provider: str
    error: Optional[str]  # friendly text only — never the raw exception


def transcribe_audio(audio_bytes: bytes, mime_type: str, filename: str = "audio.webm") -> TranscriptionResult:
    """Send recorded audio to Sarvam's STT endpoint. Never raises; returns a
    friendly error string on failure and logs the technical detail."""
    if not settings.SARVAM_API_KEY:
        logger.warning("[stt] STT_PROVIDER=sarvam but SARVAM_API_KEY is not set")
        return TranscriptionResult(
            ok=False,
            transcript="",
            language_code=None,
            provider="sarvam",
            error="Voice input isn't configured on the server (missing SARVAM_API_KEY).",
        )

    try:
        response = requests.post(
            _ENDPOINT,
            headers={"api-subscription-key": settings.SARVAM_API_KEY},
            files={"file": (filename, audio_bytes, mime_type)},
            data={
                "model": settings.SARVAM_STT_MODEL,
                "language_code": settings.SARVAM_STT_LANGUAGE,
            },
            timeout=_TIMEOUT_SECONDS,
        )
    except requests.exceptions.Timeout:
        logger.error("[stt] Sarvam request timed out after %ss", _TIMEOUT_SECONDS)
        return TranscriptionResult(
            ok=False, transcript="", language_code=None, provider="sarvam",
            error="Voice transcription timed out — try again in a moment.",
        )
    except requests.exceptions.RequestException as e:
        logger.error("[stt] Sarvam request failed: %s", e)
        return TranscriptionResult(
            ok=False, transcript="", language_code=None, provider="sarvam",
            error="Couldn't reach the voice transcription service — try again in a moment.",
        )

    if response.status_code == 200:
        try:
            data = response.json()
        except ValueError:
            logger.error("[stt] Sarvam returned 200 with non-JSON body: %r", response.text[:300])
            return TranscriptionResult(
                ok=False, transcript="", language_code=None, provider="sarvam",
                error="Voice transcription returned an unexpected response.",
            )
        return TranscriptionResult(
            ok=True,
            transcript=(data.get("transcript") or "").strip(),
            language_code=data.get("language_code"),
            provider="sarvam",
            error=None,
        )

    # Non-200 — log the technical detail, return a friendly message. 429/503
    # are named distinctly so the frontend can suggest "try again" for those.
    logger.error("[stt] Sarvam error %s: %s", response.status_code, response.text[:500])
    friendly = {
        400: "Voice input wasn't understood — try speaking again.",
        403: "Voice input isn't authorized on the server (check SARVAM_API_KEY).",
        422: "That audio couldn't be processed — try recording again.",
        429: "Voice transcription is rate-limited right now — try again shortly.",
        500: "The voice transcription service had an internal error — try again.",
        503: "The voice transcription service is temporarily unavailable — try again shortly.",
    }.get(response.status_code, "Voice transcription failed — try again in a moment.")
    return TranscriptionResult(
        ok=False, transcript="", language_code=None, provider="sarvam", error=friendly,
    )
