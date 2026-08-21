"""Per-provider retry and Groq/Gemini fallback for the RAG generation path."""

import logging
import time
from typing import Callable, Generator, Optional, Tuple

from app.ai.gemini_client import call_gemini, stream_gemini
from app.ai.groq_client import call_groq, stream_groq
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
    """Retry make_stream() on transient failures. Returns ("ok", generator) on
    success or ("failed", last_error_text) if every attempt failed; never yields
    itself, so the caller decides how to handle failure."""
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
    """Single-provider retry, no provider fallback."""
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
    """Try the primary with retry; on exhaustion try the fallback with its own
    retry budget; if both fail, yield a clean final error."""
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


def stream_generation(prompt: str, model: Optional[str] = None) -> Generator[str, None, None]:
    """Streaming generation entry point. `model`'s provider (via
    settings.model_provider()) sets the order: a Gemini selection runs
    Gemini-primary/Groq-fallback, anything else Groq-primary/Gemini-fallback.
    The other provider is always the fallback, so a selection changes the
    order, not the resilience."""
    provider = settings.model_provider(model)
    groq_model = model if provider == "groq" and model else settings.GROQ_MODEL

    def make_groq_stream():
        return stream_groq(prompt, model=groq_model)

    def make_gemini_stream():
        return stream_gemini(prompt, model=model)

    if provider == "gemini":
        yield from stream_with_fallback(make_gemini_stream, make_groq_stream, "Gemini", "Groq")
    else:
        yield from stream_with_fallback(make_groq_stream, make_gemini_stream, "Groq", "Gemini")


def call_generation(prompt: str, model: Optional[str] = None) -> str:
    """Non-streaming equivalent of stream_generation(): returns one complete
    string. Same provider routing."""
    provider = settings.model_provider(model)
    groq_model = model if provider == "groq" and model else settings.GROQ_MODEL

    def make_groq_call():
        yield call_groq(prompt, model=groq_model)

    def make_gemini_call():
        yield call_gemini(prompt, model=model)

    if provider == "gemini":
        return "".join(stream_with_fallback(make_gemini_call, make_groq_call, "Gemini", "Groq"))
    return "".join(stream_with_fallback(make_groq_call, make_gemini_call, "Groq", "Gemini"))
