"""Session memory — JSON-based, single shared history file.

SUPERSEDED by conversation_store.py (Phase 3) — this file is kept only as a
reference for what Phase 1/2 looked like before real multi-conversation
storage existed. No route imports this anymore. See Memory.md.
"""

import json
import os
from typing import List, Dict

from app.config import settings


def _ensure_dir() -> None:
    d = os.path.dirname(settings.HISTORY_FILE)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def load_history() -> List[Dict]:
    _ensure_dir()
    if not os.path.exists(settings.HISTORY_FILE):
        return []
    try:
        with open(settings.HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def save_history(history: List[Dict]) -> None:
    _ensure_dir()
    with open(settings.HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def append_turn(history: List[Dict], role: str, content: str) -> List[Dict]:
    history.append({"role": role, "content": content})
    save_history(history)
    return history


def recent_context(history: List[Dict], turns: int = 6) -> str:
    """Flattens the last N turns into a plain-text block for prompting."""
    tail = history[-turns:]
    return "\n".join(f"{t['role']}: {t['content']}" for t in tail)
