"""Sarvam AI speech-to-text client — the hackathon-compliant STT provider.

The hackathon task requires Sarvam or ElevenLabs for STT; Web Speech API
(frontend/js/app.js, unchanged) doesn't qualify for the graded submission
but stays as the free, key-less dev/fallback path. See
app.config.settings.STT_PROVIDER for the switch, and docs/Architecture.md
for why Sarvam was picked over ElevenLabs (Indic-language focus, matching
the ai4bharat/MSMARCO-XI corpus this app retrieves against).

API reference (fetched directly from Sarvam's live docs while building
this, not from training-data memory, since API specifics like endpoint
paths and header names go stale fast):
    POST https://api.sarvam.ai/speech-to-text
    header: api-subscription-key: <key>
    multipart form: file=<audio>, model, mode, language_code, ...
    200 response: {"request_id", "transcript", "language_code", ...}
    errors: 400/403/422/429/500/503, each {"error": {"message", "code", ...}}
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
    error: Optional[str]  # user-facing, friendly — never the raw exception


def transcribe_audio(audio_bytes: bytes, mime_type: str, filename: str = "audio.webm") -> TranscriptionResult:
    """Sends recorded audio to Sarvam's REST STT endpoint and returns a
    structured result — never raises. Matches Rules.md's error handling
    policy: friendly message back to the caller, technical detail only to
    the log.
    """
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

    # Non-200 — log the technical detail, return a friendly message.
    # 429/503 specifically are the transient cases worth naming distinctly
    # (rate limit / temporary overload) since the frontend can choose to
    # suggest "try again" differently than a hard failure like 403.
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
