"""Text embeddings via Gemini, used by the RAG pipeline in app/agents/router.py.

Model name is configurable (see app/config/settings.py) rather than
hardcoded — the gemini-1.5-flash lesson from Phase 1 applies here too.

top_k_chunks() used to be a hand-rolled brute-force cosine loop over every
chunk on every call. It's now backed by app/rag/vector_store.py's
VectorStore (FAISS when available) instead — see that module's docstring
for why. At the small scale a single uploaded document's chunks run at
(typically tens of chunks, not thousands), this doesn't change behavior —
it's still an exact search — but it's now genuinely running through a real
vector index rather than Python-level iteration, and the same code path
supports the much larger MSMARCO-XI-backed knowledge base
(app/rag/ingest.py) without a second implementation to keep in sync.
"""

import math
from typing import List

from google import genai
from google.genai import types

from app.config import settings
from app.rag.vector_store import VectorStore

_client = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.GOOGLE_API_KEY)
    return _client


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Returns one embedding vector per input string, same order."""
    if not settings.GOOGLE_API_KEY or not texts:
        return [[] for _ in texts]
    try:
        result = _get_client().models.embed_content(
            model=settings.GEMINI_EMBEDDING_MODEL,
            contents=texts,
        )
        return [e.values for e in result.embeddings]
    except Exception as e:
        print(f"[embeddings] error: {e}")
        return [[] for _ in texts]


def embed_query(text: str) -> List[float]:
    vectors = embed_texts([text])
    return vectors[0] if vectors else []


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Still used directly by app/rag/guardrails.py for single-pair
    relevance checks, where standing up a whole VectorStore for one
    comparison would be pure overhead — kept as a plain function for that,
    separate from top_k_chunks' now-VectorStore-backed batch search
    below."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def top_k_chunks(query: str, chunks: List[str], embeddings: List[List[float]], k: int = 4) -> List[str]:
    """Returns the k chunks most similar to the query, best first. Builds a
    throwaway VectorStore for this call's chunks — for a single document's
    worth of chunks (the only caller today, app/agents/router.py's
    document_rag path) that's cheap; ingest.py builds and persists a
    long-lived one instead for the MSMARCO-XI knowledge base."""
    if not chunks or not embeddings:
        return []
    query_vec = embed_query(query)
    if not query_vec:
        return chunks[:k]  # embedding failed — fall back to first-k rather than nothing

    valid = [(c, e) for c, e in zip(chunks, embeddings) if e]
    if not valid:
        return chunks[:k]
    valid_chunks, valid_embeddings = zip(*valid)

    store = VectorStore(dim=len(valid_embeddings[0]))
    store.add(list(valid_embeddings), list(valid_chunks), [{} for _ in valid_chunks])
    results = store.search(query_vec, k=k)
    return [chunk for chunk, _score, _meta in results]

