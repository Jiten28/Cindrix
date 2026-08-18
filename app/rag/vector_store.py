"""Real vector store — replaces the hand-rolled brute-force cosine loop
that used to live directly in app/ai/embeddings.py's top_k_chunks().

Backed by FAISS (IndexFlatIP for small collections — exact, just no longer
a hand-written Python loop; IndexIVFFlat for large ones, a genuine
approximate-nearest-neighbor index) when available. FAISS isn't always
installed (e.g. this was built in a sandboxed session with no network to
pip-install it) — soft-imported, with an exact numpy-based fallback that
keeps the app running (correctly, just without FAISS's speed/scale
benefits) rather than crashing. The fallback logs a warning every time a
store is built so it's never silently mistaken for the real thing in a
demo or benchmark.

Vectors are L2-normalized on insert so inner product == cosine similarity
— this is what lets one index type (IndexFlatIP) serve both "exact search"
and "cosine similarity" without needing two different metrics.
"""

import json
import logging
import os
import pickle
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

try:
    import faiss
    _FAISS_AVAILABLE = True
except ImportError:
    _FAISS_AVAILABLE = False

# Above this many vectors, use an IVF (inverted file) index instead of a
# flat one — flat is exact but O(n) per query, fine up to a few tens of
# thousands of vectors; IVF trades a small amount of recall for real
# sublinear search time at MSMARCO-XI's scale.
_IVF_THRESHOLD = 10_000
_IVF_NLIST = 100  # number of coarse clusters FAISS partitions vectors into


def _normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


class VectorStore:
    """One store = one collection of (vector, chunk_text, metadata) triples
    plus whatever index structure is searching them. Doesn't know or care
    whether it's holding a handful of per-upload document chunks or a few
    thousand MSMARCO-XI passages — same class either way."""

    def __init__(self, dim: int):
        self.dim = dim
        self._chunks: List[str] = []
        self._metadata: List[Dict[str, Any]] = []
        self._vectors: Optional[np.ndarray] = None  # only kept for the numpy fallback path
        self._faiss_index = None
        self._backend = "faiss" if _FAISS_AVAILABLE else "numpy_fallback"
        if not _FAISS_AVAILABLE:
            logger.warning(
                "[rag.vector_store] faiss not installed — using an exact "
                "numpy fallback (correct, but not what's meant by 'real "
                "vector store' for the hackathon submission). "
                "`pip install faiss-cpu` and rebuild the index before relying "
                "on this for real scale/latency numbers."
            )

    def add(self, vectors: List[List[float]], chunks: List[str], metadata: List[Dict[str, Any]]) -> None:
        if not vectors:
            return
        if not (len(vectors) == len(chunks) == len(metadata)):
            raise ValueError("vectors, chunks, and metadata must be the same length")

        arr = np.asarray(vectors, dtype="float32")
        if arr.shape[1] != self.dim:
            raise ValueError(f"expected {self.dim}-dim vectors, got {arr.shape[1]}")
        arr = _normalize(arr)

        self._chunks.extend(chunks)
        self._metadata.extend(metadata)

        if self._backend == "faiss":
            if self._faiss_index is None:
                self._faiss_index = self._build_faiss_index(arr)
            else:
                self._faiss_index.add(arr)
        else:
            self._vectors = arr if self._vectors is None else np.vstack([self._vectors, arr])

    def _build_faiss_index(self, first_batch: np.ndarray):
        n = first_batch.shape[0]
        if n < _IVF_THRESHOLD:
            index = faiss.IndexFlatIP(self.dim)
            index.add(first_batch)
            return index
        # IVF needs training on representative vectors before it can add —
        # use this first batch as the training set.
        quantizer = faiss.IndexFlatIP(self.dim)
        index = faiss.IndexIVFFlat(quantizer, self.dim, _IVF_NLIST, faiss.METRIC_INNER_PRODUCT)
        index.train(first_batch)
        index.add(first_batch)
        index.nprobe = min(10, _IVF_NLIST)  # how many clusters to search — recall/speed tradeoff
        return index

    def search(self, query_vector: List[float], k: int = 4) -> List[Tuple[str, float, Dict[str, Any]]]:
        """Returns up to k (chunk_text, cosine_similarity, metadata)
        triples, best first."""
        if not self._chunks:
            return []
        q = _normalize(np.asarray([query_vector], dtype="float32"))

        if self._backend == "faiss":
            scores, indices = self._faiss_index.search(q, min(k, len(self._chunks)))
            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx == -1:
                    continue
                results.append((self._chunks[idx], float(score), self._metadata[idx]))
            return results

        # numpy fallback — exact cosine via a single vectorized matmul
        # rather than embeddings.py's old per-pair Python loop.
        sims = (self._vectors @ q[0])
        top_idx = np.argsort(-sims)[:k]
        return [(self._chunks[i], float(sims[i]), self._metadata[i]) for i in top_idx]

    def __len__(self) -> int:
        return len(self._chunks)

    # -- persistence -----------------------------------------------------

    def save(self, path: str) -> None:
        """Saves to <path>.meta.json (chunks/metadata) + <path>.faiss or
        <path>.npy (the vectors/index itself, depending on backend)."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(f"{path}.meta.json", "w", encoding="utf-8") as f:
            json.dump({
                "dim": self.dim,
                "backend": self._backend,
                "chunks": self._chunks,
                "metadata": self._metadata,
            }, f, ensure_ascii=False)
        if self._backend == "faiss":
            faiss.write_index(self._faiss_index, f"{path}.faiss")
        else:
            with open(f"{path}.pkl", "wb") as f:
                pickle.dump(self._vectors, f)

    @classmethod
    def load(cls, path: str) -> "VectorStore":
        with open(f"{path}.meta.json", "r", encoding="utf-8") as f:
            meta = json.load(f)
        store = cls(dim=meta["dim"])
        store._chunks = meta["chunks"]
        store._metadata = meta["metadata"]
        saved_backend = meta["backend"]

        if saved_backend == "faiss" and _FAISS_AVAILABLE:
            store._faiss_index = faiss.read_index(f"{path}.faiss")
            store._backend = "faiss"
        elif saved_backend == "faiss" and not _FAISS_AVAILABLE:
            raise RuntimeError(
                f"Index at {path} was saved with faiss but faiss isn't installed "
                f"in this environment — install faiss-cpu to load it."
            )
        else:
            with open(f"{path}.pkl", "rb") as f:
                store._vectors = pickle.load(f)
            store._backend = "numpy_fallback"
        return store

    @staticmethod
    def exists(path: str) -> bool:
        return os.path.exists(f"{path}.meta.json")
