"""Chat API — one streaming endpoint for now (Phase 1 scope). File upload,
image, and auth routes arrive in Phase 2/4 per Phases.md."""

from flask import Blueprint, Response, jsonify, request, stream_with_context

from app.agents.router import stream_route_query
from app.memory.session_memory import append_turn, load_history

bp = Blueprint("api", __name__, url_prefix="/api")


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
