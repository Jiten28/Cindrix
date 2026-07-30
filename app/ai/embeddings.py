"""Text embeddings via Gemini, used by the RAG pipeline in app/agents/router.py.

Model name is configurable (see app/config/settings.py) rather than
hardcoded — the gemini-1.5-flash lesson from Phase 1 applies here too.
"""

import math
from typing import List

from google import genai
from google.genai import types

from app.config import settings

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
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def top_k_chunks(query: str, chunks: List[str], embeddings: List[List[float]], k: int = 4) -> List[str]:
    """Returns the k chunks most similar to the query, best first."""
    if not chunks or not embeddings:
        return []
    query_vec = embed_query(query)
    if not query_vec:
        return chunks[:k]  # embedding failed — fall back to first-k rather than nothing
    scored = [
        (cosine_similarity(query_vec, vec), chunk)
        for chunk, vec in zip(chunks, embeddings)
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [chunk for _, chunk in scored[:k]]
