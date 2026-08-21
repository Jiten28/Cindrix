"""Ingest ai4bharat/MSMARCO-XI into a persisted vector store."""

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

# Bound batch size so per-call requests don't grow unbounded with chunk count.
_EMBED_BATCH_SIZE = 32

# Batch job opts into the 429 retry budget (free tier caps embeddings at
# ~100/min), riding out the rate window so the index is complete. Live query
# embedding fails fast instead — it can't hang the request.
_EMBED_MAX_RETRIES = 6


def default_index_path(language: str) -> str:
    return f"{settings.RAG_INDEX_DIR}/msmarco_xi_{language}"


def ingest(
    language: Optional[str] = None,
    split: Optional[str] = None,
    max_rows: Optional[int] = None,
    index_path: Optional[str] = None,
) -> dict:
    """Run the full pipeline; return a stats dict."""
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
