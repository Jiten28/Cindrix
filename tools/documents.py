"""Document parsing + chunking for the RAG pipeline. Supports PDF, TXT, DOCX.

No OCR library here on purpose — Gemini's vision endpoint reads text inside
images natively (see app/ai/gemini_client.py's call_gemini_vision), which
covers the scanned-document case without adding a Tesseract dependency. If a
genuinely offline/no-API-call OCR path is ever needed, revisit this decision
— see Rules.md on adding new major dependencies.
"""

import os
from typing import List

from pypdf import PdfReader
from docx import Document as DocxDocument

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".docx"}


def extract_text(filepath: str) -> str:
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".pdf":
        return _extract_pdf(filepath)
    if ext == ".docx":
        return _extract_docx(filepath)
    if ext == ".txt":
        return _extract_txt(filepath)
    raise ValueError(f"Unsupported document type: {ext}")


def _extract_pdf(filepath: str) -> str:
    reader = PdfReader(filepath)
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages).strip()


def _extract_docx(filepath: str) -> str:
    doc = DocxDocument(filepath)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _extract_txt(filepath: str) -> str:
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 120) -> List[str]:
    """Simple character-based chunking with overlap. Good enough for a
    single-document RAG use case; swap for a sentence-aware splitter if
    retrieval quality becomes an issue with real documents."""
    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end].strip())
        start = end - overlap
    return [c for c in chunks if c]
