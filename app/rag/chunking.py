"""Chunking strategies for the RAG pipeline: fixed-size, semantic, and metadata-aware."""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class Chunk:
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    strategy: str = "unknown"


def fixed_size_chunks(
    text: str,
    chunk_size: int = 800,
    overlap: int = 120,
    metadata: Dict[str, Any] | None = None,
) -> List[Chunk]:
    """Character-window chunking with overlap."""
    text = text.strip()
    if not text:
        return []
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    base_meta = metadata or {}
    chunks: List[Chunk] = []
    start = 0
    index = 0
    while start < len(text):
        end = start + chunk_size
        piece = text[start:end].strip()
        if piece:
            chunks.append(Chunk(
                text=piece,
                metadata={**base_meta, "chunk_index": index, "strategy": "fixed_size"},
                strategy="fixed_size",
            ))
            index += 1
        start = end - overlap
    return chunks


# A regex is enough to avoid cutting mid-sentence; no NLTK/spaCy dependency.
# । is the Devanagari danda (full stop) — the corpus is Hindi/Indic, not just English.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?।])\s+")


def semantic_chunks(
    text: str,
    target_size: int = 800,
    min_size: int = 200,
    metadata: Dict[str, Any] | None = None,
) -> List[Chunk]:
    """Pack whole sentences into ~target_size chunks without splitting a sentence.

    A chunk still under min_size takes the next sentence anyway rather than
    emit a too-small chunk."""
    text = text.strip()
    if not text:
        return []

    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    if not sentences:
        return []

    base_meta = metadata or {}
    chunks: List[Chunk] = []
    current: List[str] = []
    current_len = 0
    index = 0

    def flush():
        nonlocal current, current_len, index
        if not current:
            return
        piece = " ".join(current).strip()
        if piece:
            chunks.append(Chunk(
                text=piece,
                metadata={**base_meta, "chunk_index": index, "strategy": "semantic", "sentence_count": len(current)},
                strategy="semantic",
            ))
            index += 1
        current = []
        current_len = 0

    for sentence in sentences:
        projected = current_len + len(sentence) + 1
        if current and projected > target_size and current_len >= min_size:
            flush()
        current.append(sentence)
        current_len += len(sentence) + 1

    flush()
    return chunks


def metadata_aware_chunks(row: Dict[str, Any]) -> List[Chunk]:
    """One MSMARCO-XI row -> one chunk per passage, tagged with the dataset's
    own metadata (is_selected, query_id, language). Passages are already
    self-contained retrieval units, so they're not re-split."""
    passages = row.get("passages") or {}
    translated = passages.get("Translated_passages") or []
    is_selected = passages.get("is_selected") or []
    english = passages.get("English_passages") or []

    chunks: List[Chunk] = []
    for i, passage_text in enumerate(translated):
        passage_text = (passage_text or "").strip()
        if not passage_text:
            continue
        chunks.append(Chunk(
            text=passage_text,
            metadata={
                "strategy": "metadata_aware",
                "query_id": row.get("query_id"),
                "query": row.get("query"),
                "query_type": row.get("query_type"),
                "language": row.get("target_lang"),
                "passage_index": i,
                "is_selected": bool(is_selected[i]) if i < len(is_selected) else None,
                "english_passage": english[i] if i < len(english) else None,
            },
            strategy="metadata_aware",
        ))
    return chunks
