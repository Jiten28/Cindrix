"""Tracks the 'active attachment' (uploaded document or image), keyed by an
opaque string the caller controls. Started as one slot per user_id (Phase
4), then became one slot per "user_id:conversation_id" (post-launch fix —
see routes.py's _attachment_key and Memory.md) once per-user scoping turned
out to still leak an attachment across a user's different conversations.
This module itself doesn't know or care what the key means — routes.py
builds it.
"""

import json
import os
from typing import List, Optional, TypedDict

from app.config import settings

_BASE_DIR = os.path.join(settings.EMBEDDING_DIR, "_attachments")


class Attachment(TypedDict, total=False):
    kind: str  # "document" | "image"
    filename: str
    filepath: str
    mime_type: str
    chunks: List[str]
    embeddings: List[List[float]]


def _ensure_dirs() -> None:
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(_BASE_DIR, exist_ok=True)


def _state_file(key: str) -> str:
    # Composite keys look like "user_id:conversation_id" — ":" isn't a
    # legal character in Windows filenames, so it gets swapped out here
    # rather than baked into every caller's key-building logic.
    safe_key = key.replace(":", "__")
    return os.path.join(_BASE_DIR, f"{safe_key}.json")


def set_active(key: str, attachment: Attachment) -> None:
    _ensure_dirs()
    with open(_state_file(key), "w", encoding="utf-8") as f:
        json.dump(attachment, f)


def get_active(key: str) -> Optional[Attachment]:
    path = _state_file(key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def clear_active(key: str) -> None:
    path = _state_file(key)
    if os.path.exists(path):
        os.remove(path)
