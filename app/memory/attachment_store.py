"""Tracks the 'active attachment' (uploaded document or image), scoped per
user (Phase 4) — one slot per user_id instead of one global slot. Not
logging in still works (falls under the 'guest' bucket).
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


def _state_file(user_id: str) -> str:
    return os.path.join(_BASE_DIR, f"{user_id}.json")


def set_active(user_id: str, attachment: Attachment) -> None:
    _ensure_dirs()
    with open(_state_file(user_id), "w", encoding="utf-8") as f:
        json.dump(attachment, f)


def get_active(user_id: str) -> Optional[Attachment]:
    path = _state_file(user_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def clear_active(user_id: str) -> None:
    path = _state_file(user_id)
    if os.path.exists(path):
        os.remove(path)
