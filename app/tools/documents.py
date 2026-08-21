"""Document parsing and chunking for RAG. Supports PDF, TXT, DOCX."""

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
    """Character-based chunking with overlap."""
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
