"""Retry + structured error recovery, applied specifically around the RAG
path in app/agents/router.py (document_rag and knowledge_base_rag) — not a
blanket change to every Gemini call site (weather, plain chat, etc.),
since Priority 5 scoped this to "the RAG path specifically, since that's
what's graded." See docs/Architecture.md's Harness Hardening section.

Built directly against a real failure this project hit in production: a
transient `503 UNAVAILABLE` from Gemini surfaced to the user as raw
`(Gemini error: 503 UNAVAILABLE. {'error': {'code': 503, ...}})` text in
the chat — see docs/Memory.md's dated log entry for this priority. That's
exactly the shape this module retries/recovers from.

Important constraint: app/ai/gemini_client.py's stream_gemini() catches
its own exceptions internally and *yields* an error string rather than
raising — so "was this a transient failure" is detected by pattern-
matching the first yielded chunk, not by catching an exception here.
Retries only happen before any real content has reached the caller —
once a chunk of the actual answer has been yielded, retrying from scratch
would duplicate content, so a failure after that point just closes the
stream gracefully with a short trailer note instead (per Rules.md:
"Streaming responses must gracefully close the stream on error, not hang
the UI").
"""

import logging
import time
from typing import Callable, Generator

logger = logging.getLogger(__name__)

_TRANSIENT_MARKERS = (
    "503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "rate limit",
    "timeout", "Timeout", "ConnectionError", "temporarily",
)
_MAX_RETRIES = 2
_BACKOFF_BASE_SECONDS = 0.6


def _looks_transient(text: str) -> bool:
    return any(marker in text for marker in _TRANSIENT_MARKERS)


def _is_error_chunk(text: str) -> bool:
    return text.startswith("(Gemini error:") or text.startswith("(error:")


def stream_with_retry(make_stream: Callable[[], Generator[str, None, None]]) -> Generator[str, None, None]:
    """`make_stream` is a zero-arg callable returning a FRESH generator
    each call — e.g. `lambda: stream_gemini(prompt, model=model)` — needed
    because a partially-consumed generator can't be rewound/restarted; a
    new one has to be created per retry attempt.

    Retries up to _MAX_RETRIES times with exponential backoff, but only
    while the failure is (a) detected on the very first chunk (nothing
    real sent yet) and (b) looks transient (503/429/timeout-shaped, not
    e.g. an auth error that a retry won't fix). Logs the technical detail
    each attempt; the caller only ever sees a friendly final message if
    every attempt fails.
    """
    attempt = 0
    while True:
        gen = make_stream()
        try:
            first_chunk = next(gen)
        except StopIteration:
            return  # legitimately empty response — nothing to yield, nothing to retry
        except Exception as e:
            first_chunk = f"(error: {e})"

        if _is_error_chunk(first_chunk):
            if _looks_transient(first_chunk) and attempt < _MAX_RETRIES:
                attempt += 1
                wait = _BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                logger.warning(
                    "[rag.retry] transient error on attempt %d/%d, retrying in %.1fs: %s",
                    attempt, _MAX_RETRIES + 1, wait, first_chunk,
                )
                time.sleep(wait)
                continue
            logger.error(
                "[rag.retry] RAG generation failed after %d attempt(s), giving up: %s",
                attempt + 1, first_chunk,
            )
            yield "Cindrix hit a temporary issue answering that from the knowledge base — please try again in a moment."
            return

        # Real content reached us — from here on, no more retrying (would
        # duplicate what the user already sees). Pass the rest through,
        # closing gracefully if it breaks mid-stream instead of hanging.
        yield first_chunk
        try:
            for chunk in gen:
                yield chunk
        except Exception as e:
            logger.error("[rag.retry] stream interrupted mid-response: %s", e)
            yield "\n\n*(connection interrupted — the rest of this answer may be incomplete)*"
        return
