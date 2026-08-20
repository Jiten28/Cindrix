"""Retry + structured error recovery + provider fallback, applied
specifically around the RAG path in app/agents/router.py (document_rag and
knowledge_base_rag) — not a blanket change to every generation call site
(weather, plain chat, etc.), since this was scoped to "the RAG path
specifically, since that's what's graded." See docs/Architecture.md's
"Generation Provider Chain" section.

Two layers:
1. Per-provider retry (`_attempt_with_retry`, and `stream_with_retry` built
   on it) — retries a single provider on transient-looking failures
   (503/429/timeout-shaped), gives up after _MAX_RETRIES. Built directly
   against a real failure this project hit in production: a transient
   `503 UNAVAILABLE` from Gemini surfaced to the user as raw `(Gemini
   error: 503 UNAVAILABLE. {...})` text in the chat — see docs/Memory.md's
   dated log entry. Both app/ai/gemini_client.py's stream_gemini() and
   app/ai/groq_client.py's stream_groq() catch their own exceptions
   internally and *yield* an error string rather than raising, so "was
   this transient" is detected by pattern-matching the first yielded
   chunk, not by catching an exception here — same shape for both
   providers on purpose (see groq_client.py's docstring).
2. Provider fallback (`stream_with_fallback`, `stream_generation`) — Groq
   is the primary generation provider; if it exhausts its own retry
   budget, Gemini is tried next (also with its own retry budget); if that
   also fails, a clean user-facing message is returned. Logs which
   provider actually served the response, for demo narration and the
   latency benchmark's per-provider breakdown.

In both layers: retries/fallback only happen before any real content has
reached the caller — once a chunk of the actual answer is out, retrying or
switching providers would duplicate/contradict it, so a failure after that
point just closes the stream gracefully with a short trailer note instead
(per Rules.md: "streaming responses must gracefully close the stream on
error, not hang the UI").
"""

import logging
import time
from typing import Callable, Generator, Optional, Tuple

from app.ai.gemini_client import stream_gemini
from app.ai.groq_client import stream_groq
from app.config import settings

logger = logging.getLogger(__name__)

_TRANSIENT_MARKERS = (
    "503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "rate limit",
    "timeout", "Timeout", "ConnectionError", "temporarily",
)
_MAX_RETRIES = 2
_BACKOFF_BASE_SECONDS = 0.6

_GENERIC_FAILURE_MESSAGE = (
    "Cindrix hit a temporary issue answering that from the knowledge base — "
    "please try again in a moment."
)
_BOTH_PROVIDERS_FAILED_MESSAGE = (
    "Cindrix couldn't reach either AI provider right now — please try again "
    "in a moment."
)


def _looks_transient(text: str) -> bool:
    return any(marker in text for marker in _TRANSIENT_MARKERS)


def _is_error_chunk(text: str) -> bool:
    return text.startswith("(Gemini error:") or text.startswith("(Groq error:") or text.startswith("(error:")


def _chain_first(first_chunk: str, rest: Generator[str, None, None]) -> Generator[str, None, None]:
    yield first_chunk
    yield from rest


def _attempt_with_retry(
    make_stream: Callable[[], Generator[str, None, None]],
    provider_label: str,
) -> Tuple[str, object]:
    """Tries make_stream() with up to _MAX_RETRIES retries on transient-
    looking failures. Returns ("ok", generator) with the full response
    (first chunk already consumed for classification, chained back in) on
    success, or ("failed", last_error_text) if every attempt failed —
    never yields anything itself, so the caller decides what a failure
    means (retry a different provider, or give up).
    """
    attempt = 0
    last_error = ""
    while True:
        gen = make_stream()
        try:
            first_chunk = next(gen)
        except StopIteration:
            return ("ok", iter(()))  # legitimately empty response
        except Exception as e:
            first_chunk = f"(error: {e})"

        if _is_error_chunk(first_chunk):
            last_error = first_chunk
            if _looks_transient(first_chunk) and attempt < _MAX_RETRIES:
                attempt += 1
                wait = _BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                logger.warning(
                    "[retry] %s transient error on attempt %d/%d, retrying in %.1fs: %s",
                    provider_label, attempt, _MAX_RETRIES + 1, wait, first_chunk,
                )
                time.sleep(wait)
                continue
            logger.error(
                "[retry] %s failed after %d attempt(s), giving up on this provider: %s",
                provider_label, attempt + 1, first_chunk,
            )
            return ("failed", last_error)

        return ("ok", _chain_first(first_chunk, gen))


def _yield_with_graceful_close(gen: Generator[str, None, None], provider_label: str) -> Generator[str, None, None]:
    try:
        for chunk in gen:
            yield chunk
    except Exception as e:
        logger.error("[retry] %s stream interrupted mid-response: %s", provider_label, e)
        yield "\n\n*(connection interrupted — the rest of this answer may be incomplete)*"


def stream_with_retry(make_stream: Callable[[], Generator[str, None, None]]) -> Generator[str, None, None]:
    """Single-provider retry — kept as its own public function (unchanged
    behavior/signature from before the Groq fallback chain existed) for
    any caller that wants retry without provider fallback. `stream_generation`
    below is what app/agents/router.py actually uses for RAG-serving calls.
    """
    status, result = _attempt_with_retry(make_stream, "generation")
    if status == "failed":
        yield _GENERIC_FAILURE_MESSAGE
        return
    yield from _yield_with_graceful_close(result, "generation")


def stream_with_fallback(
    make_primary_stream: Callable[[], Generator[str, None, None]],
    make_fallback_stream: Callable[[], Generator[str, None, None]],
    primary_label: str = "primary",
    fallback_label: str = "fallback",
) -> Generator[str, None, None]:
    """Tries make_primary_stream() with retry; if it exhausts its retry
    budget, tries make_fallback_stream() with its own retry budget; if
    that also fails, yields a clean final error. Logs which provider
    actually served the response."""
    status, result = _attempt_with_retry(make_primary_stream, primary_label)
    if status == "ok":
        logger.info("[retry] response served by %s (primary)", primary_label)
        yield from _yield_with_graceful_close(result, primary_label)
        return

    primary_error = result
    logger.warning(
        "[retry] %s exhausted its retry budget — falling back to %s. %s error: %s",
        primary_label, fallback_label, primary_label, primary_error,
    )

    status2, result2 = _attempt_with_retry(make_fallback_stream, fallback_label)
    if status2 == "ok":
        logger.info("[retry] response served by %s (fallback, after %s failed)", fallback_label, primary_label)
        yield from _yield_with_graceful_close(result2, fallback_label)
        return

    fallback_error = result2
    logger.error(
        "[retry] BOTH providers failed — %s: %s | %s: %s",
        primary_label, primary_error, fallback_label, fallback_error,
    )
    yield _BOTH_PROVIDERS_FAILED_MESSAGE


def stream_generation(prompt: str, gemini_model: Optional[str] = None) -> Generator[str, None, None]:
    """Public entry point for RAG-serving generation calls
    (app/agents/router.py's document_rag and knowledge_base_rag paths).

    Groq (settings.GROQ_MODEL, fixed) is primary; Gemini (gemini_model —
    e.g. from the model-selector UI, or settings.GEMINI_MODEL if not
    given) is the fallback. See docs/Architecture.md's "Generation
    Provider Chain" section for why this order, and the honest caveat
    that the <200ms rationale is based on Groq's generally-published
    hardware speed, not yet this project's own benchmark.py numbers —
    that's Task 4, still pending as of the change that added this.
    """
    def make_groq_stream():
        return stream_groq(prompt, model=settings.GROQ_MODEL)

    def make_gemini_stream():
        return stream_gemini(prompt, model=gemini_model)

    yield from stream_with_fallback(make_groq_stream, make_gemini_stream, "Groq", "Gemini")
