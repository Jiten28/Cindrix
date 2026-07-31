"""Chat + upload + conversations + analytics API.

Phase 3 changes: /api/chat now takes a conversation_id (returned via the
X-Conversation-Id response header, since the response body itself is a
streaming plain-text reply and can't also carry JSON metadata inline) instead
of silently using one shared history file. New endpoints: /api/conversations
(list/create/get/delete), /api/conversations/<id>/export, and
/api/analytics/summary.
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


@bp.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    user_input = (data.get("message") or "").strip()
    conversation_id = data.get("conversation_id")
    if not user_input:
        return jsonify({"error": "message is required"}), 400

    if not conversation_id or not load_conversation(conversation_id):
        conv = create_conversation()
        conversation_id = conv["id"]

    append_message(conversation_id, "user", user_input)
    attachment = get_active()
    tool_used = detect_tool(user_input, attachment)
    start_time = time.time()

    def generate():
        full_reply = []
        for chunk in stream_route_query(user_input, conversation_id):
            full_reply.append(chunk)
            yield chunk
        reply_text = "".join(full_reply)
        append_message(conversation_id, "assistant", reply_text)
        latency_ms = int((time.time() - start_time) * 1000)
        events.log_chat_turn(conversation_id, tool_used, latency_ms, len(user_input))

    resp = Response(stream_with_context(generate()), mimetype="text/plain")
    resp.headers["X-Conversation-Id"] = conversation_id
    return resp


@bp.route("/conversations", methods=["POST"])
def new_conversation():
    conv = create_conversation()
    return jsonify(conv)


@bp.route("/conversations", methods=["GET"])
def get_conversations():
    return jsonify(list_conversations())


@bp.route("/conversations/<conv_id>", methods=["GET"])
def get_conversation(conv_id):
    conv = load_conversation(conv_id)
    if not conv:
        return jsonify({"error": "conversation not found"}), 404
    return jsonify(conv)


@bp.route("/conversations/<conv_id>", methods=["DELETE"])
def remove_conversation(conv_id):
    delete_conversation(conv_id)
    return jsonify({"deleted": True})


@bp.route("/conversations/<conv_id>/export", methods=["GET"])
def export_conversation(conv_id):
    conv = load_conversation(conv_id)
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
    return jsonify(events.summary())


@bp.route("/upload", methods=["POST"])
def upload():
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
        set_active({
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
    set_active({
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
    active = get_active()
    if not active:
        return jsonify({"active": False})
    return jsonify({
        "active": True,
        "kind": active["kind"],
        "filename": active["filename"],
    })


@bp.route("/attachment", methods=["DELETE"])
def remove_attachment():
    clear_active()
    return jsonify({"cleared": True})
