"""Analytics event logging + summary aggregation, stored as one JSON list."""

import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.config import settings

_EVENTS_FILE = os.path.join(settings.EMBEDDING_DIR, "..", "analytics_events.json")
_EVENTS_FILE = os.path.normpath(_EVENTS_FILE)


def _ensure_dir() -> None:
    d = os.path.dirname(_EVENTS_FILE)
    os.makedirs(d, exist_ok=True)


def _load() -> List[Dict]:
    _ensure_dir()
    if not os.path.exists(_EVENTS_FILE):
        return []
    try:
        with open(_EVENTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save(events: List[Dict]) -> None:
    _ensure_dir()
    with open(_EVENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2, ensure_ascii=False)


def log_chat_turn(user_id: str, conversation_id: str, tool_used: str, latency_ms: int, message_len: int) -> None:
    events = _load()
    events.append({
        "ts": datetime.now(timezone.utc).isoformat(),
        "event_type": "chat_turn",
        "user_id": user_id,
        "conversation_id": conversation_id,
        "tool_used": tool_used,
        "latency_ms": latency_ms,
        "message_len": message_len,
    })
    _save(events)


def summary(days: int = 14, user_id: Optional[str] = None) -> Dict:
    events = [e for e in _load() if e.get("event_type") == "chat_turn"]
    if user_id:
        events = [e for e in events if e.get("user_id") == user_id]

    tool_counts = Counter(e.get("tool_used", "general") for e in events)
    latencies = [e["latency_ms"] for e in events if isinstance(e.get("latency_ms"), (int, float))]
    avg_latency = round(sum(latencies) / len(latencies)) if latencies else 0

    by_day = defaultdict(int)
    for e in events:
        day = e["ts"][:10]  # YYYY-MM-DD
        by_day[day] += 1
    sorted_days = sorted(by_day.keys())[-days:]
    daily_counts = [{"date": d, "count": by_day[d]} for d in sorted_days]

    return {
        "total_messages": len(events),
        "average_latency_ms": avg_latency,
        "tool_usage": dict(tool_counts),
        "daily_message_counts": daily_counts,
    }


def messages_per_user() -> Dict[str, int]:
    """Chat-turn count per user, for the admin panel."""
    events = [e for e in _load() if e.get("event_type") == "chat_turn"]
    counts: Dict[str, int] = defaultdict(int)
    for e in events:
        counts[e.get("user_id", "guest")] += 1
    return dict(counts)
