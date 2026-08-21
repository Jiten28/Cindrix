"""Text embeddings via Gemini."""

import math
import re
import time
from collections import OrderedDict
from typing import List

from google import genai
from google.genai import types

from app.config import settings
from app.rag.vector_store import VectorStore

_client = None

# Fallback 429 retry delay when the server doesn't advise one (free-tier
# embedding quota is ~100 contents/min).
_EMBED_RETRY_DEFAULT_DELAY = 20.0


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.GOOGLE_API_KEY)
    return _client


def _retry_delay_seconds(error_text: str, default: float) -> float:
    """Parse the server-advised retry delay from a 429 error string; fall back
    to `default` if absent. Adds 1s so we resume just past the rate window."""
    for pattern in (r"retry in ([0-9.]+)s", r"retryDelay['\"]?:\s*['\"]?([0-9.]+)s"):
        match = re.search(pattern, error_text)
        if match:
            try:
                return float(match.group(1)) + 1.0
            except ValueError:
                pass
    return default


def embed_texts(
    texts: List[str],
    max_retries: int = 0,
    task_type: str = "RETRIEVAL_DOCUMENT",
) -> List[List[float]]:
    """One embedding vector per input string, same order. Retries up to
    `max_retries` times on 429; the default 0 keeps live query embedding
    fail-fast — it must not block ~45s on a rate window mid-request. A chunk
    that still fails comes back as an empty list for callers to skip.

    task_type puts documents and queries in the same asymmetric space Gemini
    was trained for; index and query side must agree or similarity scores drop."""
    if not settings.GOOGLE_API_KEY or not texts:
        return [[] for _ in texts]
    attempt = 0
    while True:
        try:
            result = _get_client().models.embed_content(
                model=settings.GEMINI_EMBEDDING_MODEL,
                contents=texts,
                config=types.EmbedContentConfig(task_type=task_type),
            )
            return [e.values for e in result.embeddings]
        except Exception as e:
            msg = str(e)
            rate_limited = "429" in msg or "RESOURCE_EXHAUSTED" in msg
            if rate_limited and attempt < max_retries:
                attempt += 1
                delay = _retry_delay_seconds(msg, _EMBED_RETRY_DEFAULT_DELAY)
                print(f"[embeddings] rate-limited (429); retry {attempt}/{max_retries} in {delay:.0f}s")
                time.sleep(delay)
                continue
            print(f"[embeddings] error: {e}")
            return [[] for _ in texts]


# Query embedding is a ~200ms network round trip and the single largest fixed
# cost in a retrieval request, so repeats are served from memory. Bounded to
# keep a long-lived worker from growing without limit; only successful
# embeddings are cached, so a transient failure isn't remembered.
_QUERY_CACHE_MAX = 256
_query_cache: "OrderedDict[str, List[float]]" = OrderedDict()


def embed_query(text: str) -> List[float]:
    key = text.strip()
    cached = _query_cache.get(key)
    if cached is not None:
        _query_cache.move_to_end(key)
        return cached

    vector = embed_texts([text], task_type="RETRIEVAL_QUERY")[0]
    if vector:
        _query_cache[key] = vector
        if len(_query_cache) > _QUERY_CACHE_MAX:
            _query_cache.popitem(last=False)
    return vector


def cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def top_k_chunks(query: str, chunks: List[str], embeddings: List[List[float]], k: int = 4) -> List[str]:
    """The k chunks most similar to the query, best first."""
    if not chunks or not embeddings:
        return []
    query_vec = embed_query(query)
    if not query_vec:
        return chunks[:k]  # embedding failed; return first-k rather than nothing

    valid = [(c, e) for c, e in zip(chunks, embeddings) if e]
    if not valid:
        return chunks[:k]
    valid_chunks, valid_embeddings = zip(*valid)

    store = VectorStore(dim=len(valid_embeddings[0]))
    store.add(list(valid_embeddings), list(valid_chunks), [{} for _ in valid_chunks])
    results = store.search(query_vec, k=k)
    return [chunk for chunk, _score, _meta in results]

