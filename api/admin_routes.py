"""Basic admin panel API — user list + usage stats. Gated by is_admin on the
requesting session's user (see app/auth/current_user.py — the first account
ever created is auto-flagged admin)."""

from flask import Blueprint, jsonify

from app.analytics.events import messages_per_user, summary
from app.auth.current_user import is_admin
from app.auth.users_store import list_users
from app.memory.conversation_store import count_conversations

bp = Blueprint("admin", __name__, url_prefix="/api/admin")


def _require_admin():
    if not is_admin():
        return jsonify({"error": "admin access required"}), 403
    return None


@bp.route("/users", methods=["GET"])
def users():
    denied = _require_admin()
    if denied:
        return denied

    msg_counts = messages_per_user()
    result = []
    for u in list_users():
        result.append({
            **u,
            "message_count": msg_counts.get(u["id"], 0),
            "conversation_count": count_conversations(u["id"]),
        })
    return jsonify(result)


@bp.route("/stats", methods=["GET"])
def stats():
    denied = _require_admin()
    if denied:
        return denied
    return jsonify(summary())
