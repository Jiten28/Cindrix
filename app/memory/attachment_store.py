"""Tracks the active attachment (document or image) per caller-supplied key."""

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
    # ":" isn't legal in Windows filenames, so swap it for the on-disk name.
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
