"""FAISS-backed vector store (IndexFlatIP for small collections, IndexIVFFlat for
large ones) with an exact numpy fallback when faiss isn't importable. Vectors are
L2-normalized on insert so inner product == cosine similarity.

Every saved index carries a <path>.vectors.npy sidecar of the raw vectors, so an
index built with faiss still loads and searches where faiss can't be imported —
see save() for why that case is real rather than theoretical."""

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

# Above this many vectors, use an approximate IVF index instead of an exact flat one.
_IVF_THRESHOLD = 10_000
_IVF_NLIST = 100  # coarse clusters FAISS partitions vectors into


def _normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


class VectorStore:
    """A collection of (vector, chunk_text, metadata) triples plus its search index."""

    def __init__(self, dim: int):
        self.dim = dim
        self._chunks: List[str] = []
        self._metadata: List[Dict[str, Any]] = []
        self._vectors: Optional[np.ndarray] = None  # only kept for the numpy fallback
        self._faiss_index = None
        self._backend = "faiss" if _FAISS_AVAILABLE else "numpy_fallback"
        if not _FAISS_AVAILABLE:
            logger.warning(
                "[rag.vector_store] faiss not importable — using an exact "
                "numpy fallback (correct, and fine at this corpus size, but "
                "slow at scale). If faiss-cpu is installed and this still "
                "fires, the wheel's OpenMP runtime is missing: install "
                "libgomp1 (Debian/Ubuntu slim images omit it)."
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
        # IVF must be trained before it can add; use the first batch as training data.
        quantizer = faiss.IndexFlatIP(self.dim)
        index = faiss.IndexIVFFlat(quantizer, self.dim, _IVF_NLIST, faiss.METRIC_INNER_PRODUCT)
        index.train(first_batch)
        index.add(first_batch)
        index.nprobe = min(10, _IVF_NLIST)  # clusters searched — recall/speed tradeoff
        return index

    def search(self, query_vector: List[float], k: int = 4) -> List[Tuple[str, float, Dict[str, Any]]]:
        """Returns up to k (chunk_text, cosine_similarity, metadata) triples, best first."""
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

        # numpy fallback: exact cosine via one vectorized matmul.
        sims = (self._vectors @ q[0])
        top_idx = np.argsort(-sims)[:k]
        return [(self._chunks[i], float(sims[i]), self._metadata[i]) for i in top_idx]

    def __len__(self) -> int:
        return len(self._chunks)

    @property
    def metadatas(self) -> List[Dict[str, Any]]:
        """Per-chunk metadata in index order — lets callers see what's indexed
        (the benchmark draws its test queries from here)."""
        return self._metadata

    # -- persistence -----------------------------------------------------

    def save(self, path: str) -> None:
        """Saves <path>.meta.json (chunks/metadata) plus <path>.faiss or <path>.pkl,
        and always a <path>.vectors.npy sidecar of the raw normalized vectors.

        The sidecar exists because the index has to be readable in environments
        the build machine can't verify. A .faiss file needs faiss to read, and
        faiss's wheel needs an OpenMP runtime that slim base images omit — so an
        index saved here would otherwise be unloadable in a container that could
        still search it perfectly well with numpy. It costs one float32 copy of
        the vectors on disk to make the numpy fallback a real fallback rather
        than a build-time-only one."""
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
        self._save_vector_sidecar(path)

    def _save_vector_sidecar(self, path: str) -> None:
        vectors = self._raw_vectors()
        if vectors is None:
            logger.warning(
                "[rag.vector_store] could not extract raw vectors — saved "
                "without a .vectors.npy sidecar, so this index will only load "
                "where faiss is importable."
            )
            return
        np.save(f"{path}.vectors.npy", vectors)

    def _raw_vectors(self) -> Optional[np.ndarray]:
        """The normalized vectors as one array, whichever backend holds them."""
        if self._vectors is not None:
            return self._vectors
        if self._faiss_index is None:
            return None
        try:
            return self._faiss_index.reconstruct_n(0, self._faiss_index.ntotal)
        except Exception as e:
            # IVF indexes need make_direct_map() before reconstruct_n; try it
            # once rather than silently giving up on the sidecar.
            try:
                self._faiss_index.make_direct_map()
                return self._faiss_index.reconstruct_n(0, self._faiss_index.ntotal)
            except Exception:
                logger.warning("[rag.vector_store] reconstruct_n unavailable: %s", e)
                return None

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
            return store

        if saved_backend == "faiss":
            # faiss isn't importable here. The .faiss file is unreadable without
            # it, but the sidecar is just an array — search exactly with numpy
            # instead of refusing to load an index that is otherwise fine.
            sidecar = f"{path}.vectors.npy"
            if not os.path.exists(sidecar):
                raise RuntimeError(
                    f"Index at {path} was saved with faiss, faiss isn't installed "
                    f"here, and there is no {os.path.basename(sidecar)} sidecar to "
                    f"fall back to. Install faiss-cpu (it needs libgomp1 on Debian "
                    f"slim images) or rebuild the index to generate the sidecar."
                )
            logger.warning(
                "[rag.vector_store] faiss not importable — loading %s from its "
                "numpy sidecar and searching exactly. Correct, but slower than "
                "faiss at scale.", path,
            )
            store._vectors = np.load(sidecar)
            store._backend = "numpy_fallback"
            return store

        with open(f"{path}.pkl", "rb") as f:
            store._vectors = pickle.load(f)
        store._backend = "numpy_fallback"
        return store

    @staticmethod
    def exists(path: str) -> bool:
        return os.path.exists(f"{path}.meta.json")
