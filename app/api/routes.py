"""Chat + upload API. File upload (Phase 2) adds /api/upload,
/api/attachment, and /api/attachment (DELETE) alongside the Phase 1 chat
endpoints."""

import os
import uuid

from flask import Blueprint, Response, jsonify, request, stream_with_context
from werkzeug.utils import secure_filename

from app.agents.router import stream_route_query
from app.ai.embeddings import embed_texts
from app.config import settings
from app.memory.attachment_store import clear_active, get_active, set_active
from app.memory.session_memory import append_turn, load_history
from app.tools.documents import SUPPORTED_EXTENSIONS, chunk_text, extract_text

bp = Blueprint("api", __name__, url_prefix="/api")

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
_IMAGE_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


@bp.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    user_input = (data.get("message") or "").strip()
    if not user_input:
        return jsonify({"error": "message is required"}), 400

    history = load_history()
    append_turn(history, "user", user_input)

    def generate():
        full_reply = []
        for chunk in stream_route_query(user_input, history):
            full_reply.append(chunk)
            yield chunk
        append_turn(history, "assistant", "".join(full_reply))

    return Response(stream_with_context(generate()), mimetype="text/plain")


@bp.route("/history", methods=["GET"])
def history():
    return jsonify(load_history())


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

    # document: extract, chunk, embed
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
