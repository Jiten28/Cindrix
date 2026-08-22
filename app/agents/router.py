"""Query routing: decide whether a message needs a tool (weather/crypto/search),
an active attachment (RAG/vision), a knowledge-base lookup (MSMARCO-XI), or a plain
conversational answer. Keyword-based classification."""

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

# Broad weather detection — catches "weather in X", city-first ("Hyderabad
# weather"), and Hindi ("दिल्ली का मौसम"). City extraction is a separate step
# (_extract_city); anything caught but not geocodable falls to the Gemini estimate.
_WEATHER_RE = re.compile(r"\bweather\b|\bforecast\b|मौसम", re.IGNORECASE)
_CRYPTO_RE = re.compile(r"\b(price of|cost of)\s+([a-zA-Z]+)", re.IGNORECASE)
_SEARCH_RE = re.compile(r"\bsearch(?: for)?\s+(.+)", re.IGNORECASE)
_IMAGE_RE = re.compile(r"\bimage(?:s)? of\s+(.+)", re.IGNORECASE)

_kb_store: Optional[VectorStore] = None
_kb_store_load_attempted = False

# Shared preamble for every prompt in this module. The identity clause is
# explicit on purpose: asked "who created you?", the underlying model otherwise
# answers with its own provider's name instead of the product's.
_PERSONA = (
    "You are Cindrix, a helpful, concise AI assistant. If you are asked about "
    "your own identity, you are Cindrix — you run on third-party language "
    "models but are not their default assistant, so never claim to be built by "
    "whoever trained them."
)


def get_kb_store() -> Optional[VectorStore]:
    """Lazily load the persisted MSMARCO-XI index once per process (cached).
    Returns None if no index has been built yet, so the app falls through to
    plain conversational answering."""
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


# City extraction patterns, tried in order. City names can be non-ASCII, so
# none restrict the capture to [a-zA-Z]:
#   1. Hindi postposition: "दिल्ली का मौसम"   2. English preposition: "weather in Delhi"
#   3. city-first: "Hyderabad weather"
_CITY_HINDI_RE = re.compile(r"(.+?)\s*(?:का|के|की|में)\s*(?:मौसम|तापमान)")
_CITY_PREP_RE = re.compile(r"\b(?:in|for|at|of)\s+(.+)", re.IGNORECASE)
_CITY_FIRST_RE = re.compile(r"(.+?)\s+(?:weather|forecast|temperature)\b", re.IGNORECASE)

# Filler words that can survive into a capture — stripped before geocoding.
_CITY_NOISE_RE = re.compile(
    r"\b(weather|forecast|temperature|today|tonight|tomorrow|right now|now|"
    r"currently|like|what'?s|whats|what|is|the|please|tell me|it|there|"
    r"going to be|gonna be|will|be)\b|मौसम|तापमान|क्या|है|बताओ|बताइए",
    re.IGNORECASE,
)


def _clean_city(raw: str) -> str:
    """Strip filler/weather words and punctuation from a candidate city.
    Returns '' if nothing meaningful is left (caller uses the default)."""
    city = _CITY_NOISE_RE.sub("", raw)
    city = re.sub(r"\s+", " ", city).strip(" ?.!,-'\"")
    return city


def _extract_city(text: str, default: str = "your area") -> str:
    t = text.strip()
    for pattern in (_CITY_HINDI_RE, _CITY_PREP_RE, _CITY_FIRST_RE):
        match = pattern.search(t)
        if match:
            city = _clean_city(match.group(1))
            if city:
                return city
    return default


def detect_tool(user_input: str, attachment: Optional[Dict] = None) -> str:
    """Pure classification (no network calls) — mirrors the checks in
    stream_route_query so the analytics label matches what actually answered.
    knowledge_base_rag means the query was worth checking against the corpus;
    the turn can still decline or fall through to a conversational answer
    depending on how well the retrieved chunks score."""
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
    """Non-streaming route for tool-backed answers (weather/crypto/image-search).
    Web search is handled in stream_route_query since its answer is streamed
    through Gemini. Returns '' when the message isn't a tool query."""
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

    return ""  # not a tool query — caller falls through to Gemini/search


def stream_route_query(
    user_input: str,
    user_id: str,
    conversation_id: str,
    model: Optional[str] = None,
    user_display_name: Optional[str] = None,
) -> Generator[str, None, None]:
    """Streaming entry point for /api/chat. Tool answers are yielded as one
    chunk; model answers stream token by token.

    Order: unsafe-input guardrail, explicit tool intent (weather/crypto/search),
    active attachment (document -> RAG, image -> vision), knowledge-base RAG,
    then plain chat. A tool query still wins even with an attachment present."""
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
            f"{_PERSONA}{name_context} "
            f"Use the following live web search results to answer the user's "
            f"question. Mention sources naturally where it helps, but keep it "
            f"conversational rather than a raw list.\n\n"
            f"Search results:\n{context_block}\n\n"
            f"User question: {query}\nCindrix:"
        )
        yield from stream_generation(prompt, model=model)
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
                f"{_PERSONA}{name_context} "
                f"The user has uploaded a document called '{attachment['filename']}'. Use the "
                f"following excerpts from it to answer their question. If the "
                f"excerpts don't contain the answer, say so rather than guessing.\n\n"
                f"Document excerpts:\n{context_block}\n\n"
                f"User question: {user_input}\nCindrix:"
            )
            yield from stream_generation(prompt, model=model)
            return

    # ---- knowledge-base RAG (MSMARCO-XI) -------------------------------
    # Only for queries worth checking against the corpus (is_offtopic_for_kb
    # screens out greetings/tool-shaped/trivial input) and only if an index
    # has been built — otherwise this block is a no-op and behavior falls
    # through to plain conversational.
    if not attachment and not guardrails.is_offtopic_for_kb(user_input, "general"):
        kb_store = get_kb_store()
        if kb_store is not None:
            query_vector = embed_query(user_input)
            if not query_vector:
                # Embedding failed (missing/limited key, quota, network). The
                # corpus may well hold the answer — we just can't look. Say so
                # distinctly instead of logging it as "corpus not relevant",
                # which reads as a retrieval result rather than an outage.
                logger.warning(
                    "[router] query embedding unavailable — skipping "
                    "knowledge-base retrieval and answering conversationally. "
                    "Check GOOGLE_API_KEY and its embedding quota. Query: %r",
                    user_input[:80],
                )
                retrieved = []
            else:
                retrieved = kb_store.search(query_vector, k=4)
            decision = guardrails.kb_decision(retrieved)
            top_score = retrieved[0][1] if retrieved else 0.0

            if decision == guardrails.KB_ANSWER:
                context_block = "\n\n---\n\n".join(text for text, _score, _meta in retrieved)
                prompt = (
                    f"{_PERSONA}{name_context} "
                    f"Use ONLY the following excerpts from the indexed knowledge base to "
                    f"answer the user's question. If the excerpts don't fully answer it, "
                    f"say what's missing rather than filling the gap with outside "
                    f"knowledge.\n\n"
                    f"Knowledge base excerpts:\n{context_block}\n\n"
                    f"User question: {user_input}\nCindrix:"
                )
                yield from stream_generation(prompt, model=model)
                return

            if decision == guardrails.KB_DECLINE:
                logger.info(
                    "[router] knowledge-base top score %.3f is below the "
                    "relevance floor but above the decline floor — declining "
                    "rather than answering from a weak match: %r",
                    top_score, user_input[:80],
                )
                yield guardrails.DECLINE_MESSAGE
                return

            # KB_FALLTHROUGH — the corpus isn't about this. Drop the retrieved
            # excerpts entirely so they can't leak into the answer, and let the
            # normal conversational path handle it. Only log a score when there
            # was a real search to score; the no-embedding case already warned.
            if retrieved:
                logger.info(
                    "[router] knowledge-base top score %.3f — corpus not relevant, "
                    "answering conversationally: %r", top_score, user_input[:80],
                )

    context = recent_context(user_id, conversation_id)
    prompt = (
        f"{_PERSONA}{name_context}\n\n"
        f"Conversation so far:\n{context}\n\n"
        f"User: {user_input}\nCindrix:"
    )
    # Plain conversational answer — same provider chain as the RAG paths
    # (Groq primary, Gemini fallback, clean error if both fail). Most-hit path.
    yield from stream_generation(prompt, model=model)
