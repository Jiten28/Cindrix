"""Chat + upload + conversations + analytics API.

Phase 3/4: /api/chat takes a conversation_id (returned via the
X-Conversation-Id response header, since the response body itself is a
streaming plain-text reply and can't also carry JSON metadata inline);
conversations, attachments, and analytics are all scoped by
current_user_id().

Post-launch fix: attachments are now scoped per-CONVERSATION, not just
per-user — a user with two open conversations used to share one attachment
between them (upload a file in chat A, ask about it in chat B, get
answers about A's file). Each conversation gets its own attachment slot now.
Uploads that happen before a conversation exists yet (the landing page, pre-
first-message) land in a "pending" slot that gets attached to whichever
conversation the next message actually creates.
"""

import io
import json
import os
import time
import uuid

from flask import Blueprint, Response, jsonify, request, send_file, stream_with_context
from werkzeug.utils import secure_filename

from app.agents.router import detect_tool, stream_route_query
from app.ai.embeddings import embed_texts
from app.analytics import events
from app.auth.current_user import current_user, current_user_id
from app.config import settings
from app.memory.attachment_store import clear_active, get_active, set_active
from app.memory.conversation_store import (
    append_message,
    create_conversation,
    delete_conversation,
    list_conversations,
    load_conversation,
)
from app.tools.documents import SUPPORTED_EXTENSIONS, chunk_text, extract_text

bp = Blueprint("api", __name__, url_prefix="/api")

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
_IMAGE_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
_PENDING = "__pending__"


def _attachment_key(user_id: str, conversation_id: str | None) -> str:
    return f"{user_id}:{conversation_id or _PENDING}"


@bp.route("/models", methods=["GET"])
def models():
    return jsonify(settings.AVAILABLE_MODELS)


@bp.route("/chat", methods=["POST"])
def chat():
    user_id = current_user_id()
    user = current_user()
    user_display_name = user["display_name"] if user else None
    data = request.get_json(silent=True) or {}
    user_input = (data.get("message") or "").strip()
    conversation_id = data.get("conversation_id")
    model = data.get("model")
    if not user_input:
        return jsonify({"error": "message is required"}), 400

    is_new_conversation = not conversation_id or not load_conversation(user_id, conversation_id)
    if is_new_conversation:
        conv = create_conversation(user_id)
        conversation_id = conv["id"]

        # Carry over any attachment uploaded before this conversation
        # existed (e.g. from the landing page) into the new conversation's
        # own slot, then clear the pending one.
        pending = get_active(_attachment_key(user_id, None))
        if pending:
            set_active(_attachment_key(user_id, conversation_id), pending)
            clear_active(_attachment_key(user_id, None))

    append_message(user_id, conversation_id, "user", user_input)
    attachment = get_active(_attachment_key(user_id, conversation_id))
    tool_used = detect_tool(user_input, attachment)
    start_time = time.time()

    def generate():
        full_reply = []
        for chunk in stream_route_query(
            user_input, user_id, conversation_id, model=model, user_display_name=user_display_name
        ):
            full_reply.append(chunk)
            yield chunk
        reply_text = "".join(full_reply)
        append_message(user_id, conversation_id, "assistant", reply_text)
        latency_ms = int((time.time() - start_time) * 1000)
        events.log_chat_turn(user_id, conversation_id, tool_used, latency_ms, len(user_input))

    resp = Response(stream_with_context(generate()), mimetype="text/plain")
    resp.headers["X-Conversation-Id"] = conversation_id
    return resp


@bp.route("/conversations", methods=["POST"])
def new_conversation():
    conv = create_conversation(current_user_id())
    return jsonify(conv)


@bp.route("/conversations", methods=["GET"])
def get_conversations():
    return jsonify(list_conversations(current_user_id()))


@bp.route("/conversations/<conv_id>", methods=["GET"])
def get_conversation(conv_id):
    conv = load_conversation(current_user_id(), conv_id)
    if not conv:
        return jsonify({"error": "conversation not found"}), 404
    return jsonify(conv)


@bp.route("/conversations/<conv_id>", methods=["DELETE"])
def remove_conversation(conv_id):
    user_id = current_user_id()
    delete_conversation(user_id, conv_id)
    clear_active(_attachment_key(user_id, conv_id))
    return jsonify({"deleted": True})


@bp.route("/conversations/<conv_id>/export", methods=["GET"])
def export_conversation(conv_id):
    conv = load_conversation(current_user_id(), conv_id)
    if not conv:
        return jsonify({"error": "conversation not found"}), 404

    fmt = request.args.get("format", "md")
    safe_title = secure_filename(conv["title"])[:40] or "conversation"

    if fmt == "json":
        buf = io.BytesIO(json.dumps(conv, indent=2, ensure_ascii=False).encode("utf-8"))
        return send_file(buf, mimetype="application/json", as_attachment=True,
                          download_name=f"{safe_title}.json")

    lines = [f"# {conv['title']}", ""]
    for m in conv["messages"]:
        speaker = "You" if m["role"] == "user" else "Nimbus"
        lines.append(f"**{speaker}** ({m.get('ts', '')}):")
        lines.append("")
        lines.append(m["content"])
        lines.append("")
    buf = io.BytesIO("\n".join(lines).encode("utf-8"))
    return send_file(buf, mimetype="text/markdown", as_attachment=True,
                      download_name=f"{safe_title}.md")


@bp.route("/analytics/summary", methods=["GET"])
def analytics_summary():
    # Each user sees only their own usage — admins get the full picture via
    # /api/admin/stats instead.
    return jsonify(events.summary(user_id=current_user_id()))


@bp.route("/upload", methods=["POST"])
def upload():
    user_id = current_user_id()
    conversation_id = request.form.get("conversation_id") or None
    key = _attachment_key(user_id, conversation_id)

    if "file" not in request.files:
        return jsonify({"error": "no file provided"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "empty filename"}), 400

    filename = secure_filename(file.filename)
    ext = os.path.splitext(filename)[1].lower()

    if ext not in SUPPORTED_EXTENSIONS and ext not in _IMAGE_EXTENSIONS:
        allowed = sorted(SUPPORTED_EXTENSIONS | _IMAGE_EXTENSIONS)
        return jsonify({"error": f"unsupported file type '{ext}'. Allowed: {allowed}"}), 400

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    unique_name = f"{uuid.uuid4().hex}_{filename}"
    filepath = os.path.join(settings.UPLOAD_DIR, unique_name)
    file.save(filepath)

    size_mb = os.path.getsize(filepath) / (1024 * 1024)
    if size_mb > settings.MAX_UPLOAD_MB:
        os.remove(filepath)
        return jsonify({"error": f"file too large ({size_mb:.1f}MB, max {settings.MAX_UPLOAD_MB}MB)"}), 400

    if ext in _IMAGE_EXTENSIONS:
        set_active(key, {
            "kind": "image",
            "filename": filename,
            "filepath": filepath,
            "mime_type": _IMAGE_MIME[ext],
        })
        return jsonify({"kind": "image", "filename": filename})

    try:
        text = extract_text(filepath)
    except Exception as e:
        return jsonify({"error": f"couldn't read document: {e}"}), 400

    if not text.strip():
        return jsonify({"error": "no extractable text found in that document"}), 400

    chunks = chunk_text(text)
    embeddings = embed_texts(chunks)
    set_active(key, {
        "kind": "document",
        "filename": filename,
        "filepath": filepath,
        "mime_type": "",
        "chunks": chunks,
        "embeddings": embeddings,
    })
    return jsonify({"kind": "document", "filename": filename, "chunks": len(chunks)})


@bp.route("/attachment", methods=["GET"])
def attachment():
    user_id = current_user_id()
    conversation_id = request.args.get("conversation_id") or None
    active = get_active(_attachment_key(user_id, conversation_id))
    if not active:
        return jsonify({"active": False})
    return jsonify({
        "active": True,
        "kind": active["kind"],
        "filename": active["filename"],
    })


@bp.route("/attachment", methods=["DELETE"])
def remove_attachment():
    user_id = current_user_id()
    data = request.get_json(silent=True) or {}
    conversation_id = data.get("conversation_id") or request.args.get("conversation_id") or None
    clear_active(_attachment_key(user_id, conversation_id))
    return jsonify({"cleared": True})
