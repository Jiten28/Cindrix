"""Query routing — decides whether a message needs a tool (weather/crypto/
search), an active attachment (RAG/vision), a knowledge-base RAG lookup
(MSMARCO-XI, hackathon track), or a plain conversational answer.
Ported from handle_query() in gemini_retrieval.py; still keyword-based for
Phase 1 (Rules.md/Architecture.md flag upgrading this to real intent
classification as a later-phase task — don't jump ahead of it).

Phase 3 added detect_tool() as a single source of truth for "which path will
this message take" — used both to actually answer it and to label the
analytics event. Phase 4 threads user_id through (conversations and
attachments are now per-user) and an optional model override (model
selector UI).

Hackathon Phase 2 (Priorities 2/4/5 — see docs/Memory.md's dated entry)
added the knowledge_base_rag path: general queries (no tool intent, no
active attachment) are checked against the persisted MSMARCO-XI vector
store (app/rag/vector_store.py) before falling through to plain
conversational answering. Guardrails (app/rag/guardrails.py) gate both
ends of this — an unsafe-input check up front, and a grounding check on
the retrieved passages before answering from them, declining honestly
rather than letting Gemini improvise from weak/irrelevant context. Both
RAG-serving generation calls (this new path and the existing document_rag
one) go through app/ai/retry.py's stream_generation() — Groq primary,
Gemini fallback, retried and error-recovered at each step — see that
module's docstring for the real 503 this was originally built against and
docs/Architecture.md's "Generation Provider Chain" section for the
Groq-primary reasoning.
"""

import logging
import re
from typing import Dict, Generator, List, Optional

from app.ai.embeddings import embed_query, top_k_chunks
from app.ai.gemini_client import stream_gemini_vision
from app.ai.retry import stream_generation
from app.config import settings
from app.memory.attachment_store import get_active
from app.memory.conversation_store import recent_context
from app.tools.crypto import get_crypto_price
from app.tools.search import image_search, web_search
from app.tools.weather import get_weather
from app.rag import guardrails
from app.rag.ingest import default_index_path
from app.rag.vector_store import VectorStore

logger = logging.getLogger(__name__)

_WEATHER_RE = re.compile(r"\bweather\b.*\bin\s+([a-zA-Z\s]+)", re.IGNORECASE)
_CRYPTO_RE = re.compile(r"\b(price of|cost of)\s+([a-zA-Z]+)", re.IGNORECASE)
_SEARCH_RE = re.compile(r"\bsearch(?: for)?\s+(.+)", re.IGNORECASE)
_IMAGE_RE = re.compile(r"\bimage(?:s)? of\s+(.+)", re.IGNORECASE)

_kb_store: Optional[VectorStore] = None
_kb_store_load_attempted = False


def get_kb_store() -> Optional[VectorStore]:
    """Lazily loads the persisted MSMARCO-XI knowledge-base index (built by
    `python -m app.rag.ingest`) once per process, cached afterward. Returns
    None — not an error — if it hasn't been built yet, so a dev environment
    with no index built falls straight through to the pre-hackathon plain
    conversational behavior, unchanged."""
    global _kb_store, _kb_store_load_attempted
    if _kb_store_load_attempted:
        return _kb_store
    _kb_store_load_attempted = True
    path = default_index_path(settings.RAG_DATASET_LANGUAGE)
    if not VectorStore.exists(path):
        logger.info("[router] no knowledge-base index at %s yet — run `python -m app.rag.ingest` to build one", path)
        return None
    try:
        _kb_store = VectorStore.load(path)
        logger.info("[router] loaded knowledge-base index (%d chunks) from %s", len(_kb_store), path)
    except Exception as e:
        logger.error("[router] failed to load knowledge-base index at %s: %s", path, e)
        _kb_store = None
    return _kb_store


def _extract_city(text: str, default: str = "your area") -> str:
    match = _WEATHER_RE.search(text)
    return match.group(1).strip() if match else default


def detect_tool(user_input: str, attachment: Optional[Dict] = None) -> str:
    """Pure classification, no side effects — mirrors the checks in
    route_query()/stream_route_query() exactly, so analytics logging always
    matches what actually answered the message.

    "No side effects" here means no network calls (no embedding, no LLM
    call) — knowledge_base_rag is labeled based on the query passing the
    cheap guardrails.is_offtopic_for_kb heuristic and an index existing on
    disk, NOT on whether retrieval actually finds a good match (that would
    mean embedding the query twice — once here, once for real in
    stream_route_query). A message labeled knowledge_base_rag can still
    end up declining to answer if grounding turns out weak — see
    stream_route_query below."""
    text = user_input.strip()
    if guardrails.is_unsafe(text):
        return "unsafe_declined"
    if _WEATHER_RE.search(text):
        return "weather"
    if _CRYPTO_RE.search(text):
        return "crypto"
    if _IMAGE_RE.search(text):
        return "image_search"
    if _SEARCH_RE.search(text):
        return "web_search"
    if attachment:
        if attachment["kind"] == "image":
            return "image_vision"
        if attachment["kind"] == "document":
            return "document_rag"
    if not guardrails.is_offtopic_for_kb(text, "general") and get_kb_store() is not None:
        return "knowledge_base_rag"
    return "general"


def route_query(user_input: str, history: List[Dict]) -> str:
    """Non-streaming route — used for tool-backed answers where there's no
    meaningful token-by-token output (weather/crypto/image-search results).
    General web search is handled in stream_route_query instead, since its
    answer is synthesized through Gemini (streamed), not returned raw."""
    text = user_input.strip()

    if _WEATHER_RE.search(text):
        city = _extract_city(text)
        return get_weather(city)

    crypto_match = _CRYPTO_RE.search(text)
    if crypto_match:
        coin = crypto_match.group(2)
        result = get_crypto_price(coin)
        return result or f"Sorry, I couldn't find a price for '{coin}'."

    image_match = _IMAGE_RE.search(text)
    if image_match:
        results = image_search(image_match.group(1))
        if not results:
            return "No image results found (or image search isn't configured — see .env.example)."
        return "\n".join(f"- {r['title']}: {r['link']}" for r in results)

    return ""  # signals "not a tool query" — caller falls through to Gemini/search


def stream_route_query(
    user_input: str,
    user_id: str,
    conversation_id: str,
    model: Optional[str] = None,
    user_display_name: Optional[str] = None,
) -> Generator[str, None, None]:
    """Streaming entry point used by the /api/chat SSE route. Tool answers are
    yielded as one chunk (they're already complete); Gemini answers stream
    token by token.

    Priority order: unsafe-input guardrail first (declines immediately,
    before any tool/RAG/generation work happens), then explicit tool intent
    (weather/crypto/search), then an active attachment (uploaded document →
    RAG, uploaded image → vision), then the knowledge-base RAG path
    (MSMARCO-XI, hackathon track — general queries only, see
    guardrails.is_offtopic_for_kb), then a plain conversational answer. An
    uploaded file doesn't hijack every message — "what's the weather" still
    checks the weather even with a document attached — but once tool intent
    is ruled out, the attachment gets first shot at answering before the
    knowledge base or plain chat.
    """
    if guardrails.is_unsafe(user_input):
        yield guardrails.UNSAFE_DECLINE_MESSAGE
        return

    tool_answer = route_query(user_input, [])
    if tool_answer:
        yield tool_answer
        return

    name_context = f" The user's name is {user_display_name}." if user_display_name else ""

    search_match = _SEARCH_RE.search(user_input.strip())
    if search_match:
        query = search_match.group(1)
        results = web_search(query)
        if not results:
            yield "No search results found (or search isn't configured — see .env.example)."
            return
        context_block = "\n\n".join(
            f"{r['title']}\n{r['link']}\n{r['snippet']}" for r in results
        )
        prompt = (
            f"You are Cindrix, a helpful, concise AI assistant.{name_context} "
            f"Use the following live web search results to answer the user's "
            f"question. Mention sources naturally where it helps, but keep it "
            f"conversational rather than a raw list.\n\n"
            f"Search results:\n{context_block}\n\n"
            f"User question: {query}\nCindrix:"
        )
        # Same generation provider chain as the RAG paths below — this
        # used to call stream_gemini directly, which is exactly the raw-
        # error-leak bug Priority 5 was meant to fix, just on a path that
        # wasn't wired up yet. See app/ai/retry.py's stream_generation.
        yield from stream_generation(prompt, gemini_model=model)
        return

    attachment = get_active(f"{user_id}:{conversation_id}")

    if attachment:
        if attachment["kind"] == "image":
            with open(attachment["filepath"], "rb") as f:
                image_bytes = f.read()
            yield from stream_gemini_vision(user_input, image_bytes, attachment["mime_type"], model=model)
            return

        if attachment["kind"] == "document":
            relevant_chunks = top_k_chunks(
                user_input, attachment["chunks"], attachment["embeddings"], k=4
            )
            context_block = "\n\n---\n\n".join(relevant_chunks)
            prompt = (
                f"You are Cindrix, a helpful, concise AI assistant.{name_context} "
                f"The user has uploaded a document called '{attachment['filename']}'. Use the "
                f"following excerpts from it to answer their question. If the "
                f"excerpts don't contain the answer, say so rather than guessing.\n\n"
                f"Document excerpts:\n{context_block}\n\n"
                f"User question: {user_input}\nCindrix:"
            )
            # Priority 5 (retry) + Groq/Gemini fallback chain: this is
            # graded RAG output — see app/ai/retry.py's stream_generation.
            yield from stream_generation(prompt, gemini_model=model)
            return

    # ---- knowledge-base RAG (MSMARCO-XI, hackathon track) --------------
    # Only attempted for queries that look worth checking against the
    # corpus at all (guardrails.is_offtopic_for_kb screens out greetings/
    # tool-shaped/trivial input) and only if an index has actually been
    # built (`python -m app.rag.ingest`) — no index means this whole block
    # is a no-op and behavior falls through to plain conversational,
    # exactly as it worked before this priority existed.
    if not attachment and not guardrails.is_offtopic_for_kb(user_input, "general"):
        kb_store = get_kb_store()
        if kb_store is not None:
            query_vector = embed_query(user_input)
            retrieved = kb_store.search(query_vector, k=4) if query_vector else []
            if guardrails.check_grounding(retrieved):
                context_block = "\n\n---\n\n".join(text for text, _score, _meta in retrieved)
                prompt = (
                    f"You are Cindrix, a helpful, concise AI assistant.{name_context} "
                    f"Use ONLY the following excerpts from the indexed knowledge base to "
                    f"answer the user's question. If the excerpts don't fully answer it, "
                    f"say what's missing rather than filling the gap with outside "
                    f"knowledge.\n\n"
                    f"Knowledge base excerpts:\n{context_block}\n\n"
                    f"User question: {user_input}\nCindrix:"
                )
                # Priority 5 (retry) + Groq/Gemini fallback chain: this is
                # graded RAG output — see app/ai/retry.py's stream_generation.
                yield from stream_generation(prompt, gemini_model=model)
                return
            # Retrieval ran but nothing cleared the relevance floor —
            # Priority 4: decline visibly rather than let Gemini answer
            # from weak/irrelevant context.
            logger.info("[router] knowledge-base retrieval below relevance floor for: %r", user_input[:80])
            yield guardrails.DECLINE_MESSAGE
            return

    context = recent_context(user_id, conversation_id)
    prompt = (
        f"You are Cindrix, a helpful, concise AI assistant.{name_context}\n\n"
        f"Conversation so far:\n{context}\n\n"
        f"User: {user_input}\nCindrix:"
    )
    # Plain conversational answer — same provider chain as the RAG paths
    # (Groq primary, Gemini fallback, clean error if both fail). This was
    # the actual source of the "(Gemini error: 503 UNAVAILABLE...)" leak
    # confirmed live in production for general chat (weather questions,
    # factual questions) — it's the most-hit path in the whole router
    # (everything that isn't a tool, an attachment, or a knowledge-base
    # match lands here), so it was the highest-impact place this bug
    # could still exist even after Priority 5 supposedly fixed it.
    yield from stream_generation(prompt, gemini_model=model)
