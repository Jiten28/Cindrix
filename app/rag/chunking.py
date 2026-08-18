"""Chunking strategies for the RAG pipeline.

Three strategies, because different content calls for different chunking:

- fixed_size_chunks: character-window chunking with overlap. The oldest,
  simplest strategy (this is what app/tools/documents.py's chunk_text()
  already did for user-uploaded PDFs/DOCX/TXT) — good default for prose
  with no other structure to exploit.
- semantic_chunks: packs whole sentences into a chunk up to a target size,
  never cutting mid-sentence. Better for prose where cutting a sentence in
  half (fixed-size's failure mode) would hand the retriever a fragment
  that doesn't stand on its own.
- metadata_aware_chunks: for the MSMARCO-XI corpus specifically. Each
  dataset row already arrives pre-segmented into passages
  (passages.Translated_passages) — the right move here is NOT to re-chunk
  those with a text splitter (that would cut a already-coherent retrieval
  unit into meaningless fragments), it's to treat each given passage as one
  chunk and attach the metadata the dataset already provides (is_selected
  ground-truth relevance, query_id, language, source index) so retrieval
  results carry that provenance forward — see app/rag/dataset.py for where
  these fields come from and app/rag/ingest.py for how this gets used.

All three return a list of Chunk, a single shared shape so
app/rag/vector_store.py and app/agents/router.py don't need to know which
strategy produced what they're holding.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class Chunk:
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    strategy: str = "unknown"


# ---------------------------------------------------------------------------
# Strategy 1: fixed-size with overlap
# ---------------------------------------------------------------------------

def fixed_size_chunks(
    text: str,
    chunk_size: int = 800,
    overlap: int = 120,
    metadata: Dict[str, Any] | None = None,
) -> List[Chunk]:
    """Character-window chunking with overlap. Simple, predictable, no
    assumptions about sentence structure — the right default when the
    source text's structure is unknown or irregular (OCR output, tables
    flattened to text, etc.)."""
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


# ---------------------------------------------------------------------------
# Strategy 2: semantic (sentence-packed)
# ---------------------------------------------------------------------------

# Deliberately simple sentence boundary detection — a full sentence
# tokenizer (spaCy/NLTK) would be a new major dependency per Rules.md for
# a problem a regex handles well enough for chunking purposes (we don't
# need linguistic precision, just "don't cut a sentence in half").
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?।])\s+")  # includes । (Devanagari
# danda / full stop) since this pipeline runs over Hindi and other Indic-
# script text from MSMARCO-XI, not just English.


def semantic_chunks(
    text: str,
    target_size: int = 800,
    min_size: int = 200,
    metadata: Dict[str, Any] | None = None,
) -> List[Chunk]:
    """Packs whole sentences into chunks up to ~target_size characters,
    never splitting a sentence across two chunks. A chunk is closed and a
    new one started once adding the next sentence would push it past
    target_size — unless the chunk is still under min_size, in which case
    it takes the sentence anyway rather than emitting a too-small chunk."""
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


# ---------------------------------------------------------------------------
# Strategy 3: metadata-aware (dataset-native passage units)
# ---------------------------------------------------------------------------

def metadata_aware_chunks(row: Dict[str, Any]) -> List[Chunk]:
    """Turns one ai4bharat/MSMARCO-XI row into its natural passage-level
    chunks, tagging each with the retrieval-relevant metadata the dataset
    already provides. See app/rag/dataset.py for the exact row shape this
    expects (query, query_id, passages.{is_selected,Translated_passages,
    English_passages}, target_lang).

    Deliberately does NOT run a text splitter over each passage — MS
    MARCO passages are already short, self-contained retrieval units (a
    paragraph or two); re-chunking them would just as likely cut a passage
    across two fragments as it would ever produce a cleaner unit, and it
    would break the direct 1:1 link to is_selected (the dataset's own
    ground-truth relevance label) that this function exists to preserve.
    """
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
