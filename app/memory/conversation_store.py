"""Per-user multi-conversation storage, backed by JSON files."""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.config import settings

_BASE_DIR = os.path.join(settings.EMBEDDING_DIR, "..", "conversations")
_BASE_DIR = os.path.normpath(_BASE_DIR)


def _user_dir(user_id: str) -> str:
    d = os.path.join(_BASE_DIR, user_id)
    os.makedirs(d, exist_ok=True)
    return d


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conv_path(user_id: str, conv_id: str) -> str:
    return os.path.join(_user_dir(user_id), f"{conv_id}.json")


def _index_path(user_id: str) -> str:
    return os.path.join(_user_dir(user_id), "_index.json")


def _load_index(user_id: str) -> List[Dict]:
    path = _index_path(user_id)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_index(user_id: str, index: List[Dict]) -> None:
    with open(_index_path(user_id), "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)


def create_conversation(user_id: str, title: str = "New chat") -> Dict:
    conv_id = uuid.uuid4().hex[:12]
    now = _now()
    conv = {"id": conv_id, "title": title, "created_at": now, "updated_at": now, "messages": []}
    with open(_conv_path(user_id, conv_id), "w", encoding="utf-8") as f:
        json.dump(conv, f, indent=2, ensure_ascii=False)

    index = _load_index(user_id)
    index.insert(0, {"id": conv_id, "title": title, "created_at": now, "updated_at": now, "message_count": 0})
    _save_index(user_id, index)
    return conv


def list_conversations(user_id: str) -> List[Dict]:
    return _load_index(user_id)


def load_conversation(user_id: str, conv_id: str) -> Optional[Dict]:
    path = _conv_path(user_id, conv_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def append_message(user_id: str, conv_id: str, role: str, content: str) -> Optional[Dict]:
    conv = load_conversation(user_id, conv_id)
    if conv is None:
        return None
    conv["messages"].append({"role": role, "content": content, "ts": _now()})
    conv["updated_at"] = _now()

    if conv["title"] == "New chat" and role == "user":
        conv["title"] = content[:34] + ("…" if len(content) > 34 else "")

    with open(_conv_path(user_id, conv_id), "w", encoding="utf-8") as f:
        json.dump(conv, f, indent=2, ensure_ascii=False)

    index = _load_index(user_id)
    for entry in index:
        if entry["id"] == conv_id:
            entry["title"] = conv["title"]
            entry["updated_at"] = conv["updated_at"]
            entry["message_count"] = len(conv["messages"])
            break
    _save_index(user_id, index)
    return conv


def drop_last_assistant_message(user_id: str, conv_id: str) -> Optional[Dict]:
    """Remove the trailing assistant reply, if the last message is one.

    Regenerate re-answers the same user turn, so the reply being replaced has to
    go — otherwise the conversation accumulates every discarded attempt. The
    user turn itself is left alone (regenerate doesn't re-send it), and a
    conversation not ending in an assistant message is returned untouched."""
    conv = load_conversation(user_id, conv_id)
    if conv is None:
        return None
    if not conv["messages"] or conv["messages"][-1]["role"] != "assistant":
        return conv

    conv["messages"].pop()
    conv["updated_at"] = _now()
    with open(_conv_path(user_id, conv_id), "w", encoding="utf-8") as f:
        json.dump(conv, f, indent=2, ensure_ascii=False)

    index = _load_index(user_id)
    for entry in index:
        if entry["id"] == conv_id:
            entry["updated_at"] = conv["updated_at"]
            entry["message_count"] = len(conv["messages"])
            break
    _save_index(user_id, index)
    return conv


def delete_conversation(user_id: str, conv_id: str) -> bool:
    path = _conv_path(user_id, conv_id)
    if os.path.exists(path):
        os.remove(path)
    index = [e for e in _load_index(user_id) if e["id"] != conv_id]
    _save_index(user_id, index)
    return True


def recent_context(user_id: str, conv_id: str, turns: int = 6) -> str:
    conv = load_conversation(user_id, conv_id)
    if not conv:
        return ""
    tail = conv["messages"][-turns:]
    return "\n".join(f"{m['role']}: {m['content']}" for m in tail)


def count_conversations(user_id: str) -> int:
    return len(_load_index(user_id))
