"""Tracks the single 'active attachment' (uploaded document or image).

Single global slot, same shared-session simplification as
session_memory.py's conv_history.json (see Memory.md's Known Issues — this
gets revisited together with per-session isolation, not before).
"""

import json
import os
from typing import List, Optional, TypedDict

from app.config import settings

_STATE_FILE = os.path.join(settings.EMBEDDING_DIR, "_active_attachment.json")


class Attachment(TypedDict, total=False):
    kind: str  # "document" | "image"
    filename: str
    filepath: str
    mime_type: str
    chunks: List[str]
    embeddings: List[List[float]]


def _ensure_dirs() -> None:
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.EMBEDDING_DIR, exist_ok=True)


def set_active(attachment: Attachment) -> None:
    _ensure_dirs()
    with open(_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(attachment, f)


def get_active() -> Optional[Attachment]:
    if not os.path.exists(_STATE_FILE):
        return None
    try:
        with open(_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def clear_active() -> None:
    if os.path.exists(_STATE_FILE):
        os.remove(_STATE_FILE)
