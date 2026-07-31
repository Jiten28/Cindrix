"""Multi-conversation storage. Replaces session_memory.py's single shared
conv_history.json (see Memory.md's Known Issues — this is that fix).

One JSON file per conversation under data/conversations/<id>.json, plus an
index file for fast listing without reading every conversation's full
message history.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.config import settings

_CONVERSATIONS_DIR = os.path.join(settings.EMBEDDING_DIR, "..", "conversations")
_CONVERSATIONS_DIR = os.path.normpath(_CONVERSATIONS_DIR)
_INDEX_FILE = os.path.join(_CONVERSATIONS_DIR, "_index.json")


def _ensure_dir() -> None:
    os.makedirs(_CONVERSATIONS_DIR, exist_ok=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conv_path(conv_id: str) -> str:
    return os.path.join(_CONVERSATIONS_DIR, f"{conv_id}.json")


def _load_index() -> List[Dict]:
    _ensure_dir()
    if not os.path.exists(_INDEX_FILE):
        return []
    try:
        with open(_INDEX_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_index(index: List[Dict]) -> None:
    _ensure_dir()
    with open(_INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)


def create_conversation(title: str = "New chat") -> Dict:
    conv_id = uuid.uuid4().hex[:12]
    now = _now()
    conv = {"id": conv_id, "title": title, "created_at": now, "updated_at": now, "messages": []}
    _ensure_dir()
    with open(_conv_path(conv_id), "w", encoding="utf-8") as f:
        json.dump(conv, f, indent=2, ensure_ascii=False)

    index = _load_index()
    index.insert(0, {"id": conv_id, "title": title, "created_at": now, "updated_at": now, "message_count": 0})
    _save_index(index)
    return conv


def list_conversations() -> List[Dict]:
    return _load_index()


def load_conversation(conv_id: str) -> Optional[Dict]:
    path = _conv_path(conv_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def append_message(conv_id: str, role: str, content: str) -> Optional[Dict]:
    conv = load_conversation(conv_id)
    if conv is None:
        return None
    conv["messages"].append({"role": role, "content": content, "ts": _now()})
    conv["updated_at"] = _now()

    # auto-title from the first user message, same convention the frontend
    # sidebar already uses (first ~34 chars)
    if conv["title"] == "New chat" and role == "user":
        conv["title"] = content[:34] + ("…" if len(content) > 34 else "")

    with open(_conv_path(conv_id), "w", encoding="utf-8") as f:
        json.dump(conv, f, indent=2, ensure_ascii=False)

    index = _load_index()
    for entry in index:
        if entry["id"] == conv_id:
            entry["title"] = conv["title"]
            entry["updated_at"] = conv["updated_at"]
            entry["message_count"] = len(conv["messages"])
            break
    _save_index(index)
    return conv


def delete_conversation(conv_id: str) -> bool:
    path = _conv_path(conv_id)
    if os.path.exists(path):
        os.remove(path)
    index = [e for e in _load_index() if e["id"] != conv_id]
    _save_index(index)
    return True


def recent_context(conv_id: str, turns: int = 6) -> str:
    """Flattens the last N turns into a plain-text block for prompting —
    same shape session_memory.py's version had, kept for router.py
    compatibility."""
    conv = load_conversation(conv_id)
    if not conv:
        return ""
    tail = conv["messages"][-turns:]
    return "\n".join(f"{m['role']}: {m['content']}" for m in tail)
