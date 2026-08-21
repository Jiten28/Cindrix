"""Ingests ai4bharat/MSMARCO-XI into a persisted VectorStore: dataset rows
-> metadata_aware_chunks (passages are already natural retrieval units,
see chunking.py's docstring for why that strategy specifically) ->
Gemini embeddings -> VectorStore.save().

Run directly:
    python -m app.rag.ingest [--language hi] [--split train]
                              [--max-rows 2000] [--out data/rag_index/msmarco_xi_hi]

Or call ingest() programmatically — app/rag/benchmark.py's latency harness
needs a built index to benchmark retrieval against, so it can trigger this
itself with a small max_rows for a quick self-contained run.
"""

import argparse
import logging
import time
from typing import List, Optional

from app.ai.embeddings import embed_texts
from app.config import settings
from app.rag.chunking import Chunk, metadata_aware_chunks
from app.rag.dataset import load_msmarco_xi
from app.rag.vector_store import VectorStore

logger = logging.getLogger(__name__)

# Gemini's embed_content accepts a batch of texts per call — bounding batch
# size keeps individual requests from growing unbounded as chunk counts
# scale toward the full dataset.
_EMBED_BATCH_SIZE = 32

# Ingest is a batch job, so it opts into embed_texts' 429 retry budget (the
# free tier caps embeddings at ~100 contents/min — see docs/Memory.md). This
# rides out the rate window and waits rather than silently dropping chunks,
# so the persisted index is COMPLETE. Live query embedding does NOT set this
# (it must fail fast, not hang the request); see app/ai/embeddings.py.
_EMBED_MAX_RETRIES = 6


def default_index_path(language: str) -> str:
    return f"{settings.RAG_INDEX_DIR}/msmarco_xi_{language}"


def ingest(
    language: Optional[str] = None,
    split: Optional[str] = None,
    max_rows: Optional[int] = None,
    index_path: Optional[str] = None,
) -> dict:
    """Runs the full ingest pipeline; returns a stats dict rather than
    printing directly, so callers (the CLI below, benchmark.py, tests) can
    all use the same function."""
    language = language or settings.RAG_DATASET_LANGUAGE
    split = split or settings.RAG_DATASET_SPLIT
    max_rows = max_rows if max_rows is not None else settings.RAG_INGEST_MAX_ROWS
    index_path = index_path or default_index_path(language)

    all_chunks: List[Chunk] = []
    row_count = 0
    for row in load_msmarco_xi(language=language, split=split, max_rows=max_rows):
        row_count += 1
        all_chunks.extend(metadata_aware_chunks(row))

    logger.info("[rag.ingest] %d rows -> %d passage-level chunks", row_count, len(all_chunks))
    if not all_chunks:
        logger.warning("[rag.ingest] no chunks produced — nothing to index")
        return {"rows": row_count, "chunks_produced": 0, "chunks_embedded": 0, "index_path": index_path}

    texts = [c.text for c in all_chunks]
    metadatas = [c.metadata for c in all_chunks]

    vectors: List[List[float]] = []
    for i in range(0, len(texts), _EMBED_BATCH_SIZE):
        batch = texts[i:i + _EMBED_BATCH_SIZE]
        vectors.extend(embed_texts(batch, max_retries=_EMBED_MAX_RETRIES))
        logger.info("[rag.ingest] embedded %d/%d chunks", min(i + _EMBED_BATCH_SIZE, len(texts)), len(texts))

    valid = [(v, t, m) for v, t, m in zip(vectors, texts, metadatas) if v]
    skipped = len(vectors) - len(valid)
    if skipped:
        logger.warning("[rag.ingest] %d/%d chunks failed to embed (empty vector) — skipped", skipped, len(vectors))
    if not valid:
        logger.error("[rag.ingest] every embedding failed — is GOOGLE_API_KEY set?")
        return {"rows": row_count, "chunks_produced": len(all_chunks), "chunks_embedded": 0, "index_path": index_path}

    dim = len(valid[0][0])
    store = VectorStore(dim=dim)
    store.add([v for v, _, _ in valid], [t for _, t, _ in valid], [m for _, _, m in valid])
    store.save(index_path)
    logger.info("[rag.ingest] saved %d-vector index to %s", len(valid), index_path)

    return {
        "rows": row_count,
        "chunks_produced": len(all_chunks),
        "chunks_embedded": len(valid),
        "chunks_skipped": skipped,
        "index_path": index_path,
        "dim": dim,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest ai4bharat/MSMARCO-XI into a persisted vector store.")
    parser.add_argument("--language", default=None, help=f"default: {settings.RAG_DATASET_LANGUAGE}")
    parser.add_argument("--split", default=None, help=f"default: {settings.RAG_DATASET_SPLIT}")
    parser.add_argument("--max-rows", type=int, default=None, help=f"default: {settings.RAG_INGEST_MAX_ROWS}")
    parser.add_argument("--out", default=None, help="index path (without extension)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    start = time.time()
    stats = ingest(language=args.language, split=args.split, max_rows=args.max_rows, index_path=args.out)
    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.1f}s: {stats}")


if __name__ == "__main__":
    main()
