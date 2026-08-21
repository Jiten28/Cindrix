"""Auth + profile endpoints — session-based (Flask signed cookie), same-origin."""

from flask import Blueprint, jsonify, request, session

from app.auth.users_store import (
    authenticate,
    change_password,
    create_user,
    get_user,
    update_user,
    validate_password_strength,
)

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@bp.route("/signup", methods=["POST"])
def signup():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""

    if not username or not email or not password:
        return jsonify({"error": "username, email, and password are required"}), 400

    weakness = validate_password_strength(password)
    if weakness:
        return jsonify({"error": weakness}), 400

    try:
        user = create_user(username, email, password)
    except ValueError as e:
        return jsonify({"error": str(e)}), 409

    session["user_id"] = user["id"]
    return jsonify(user)


@bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    identifier = (data.get("identifier") or "").strip()
    password = data.get("password") or ""

    user = authenticate(identifier, password)
    if not user:
        return jsonify({"error": "incorrect username/email or password"}), 401

    session["user_id"] = user["id"]
    return jsonify(user)


@bp.route("/logout", methods=["POST"])
def logout():
    session.pop("user_id", None)
    return jsonify({"loggedOut": True})


@bp.route("/me", methods=["GET"])
def me():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"loggedIn": False})
    user = get_user(user_id)
    if not user:
        session.pop("user_id", None)
        return jsonify({"loggedIn": False})
    return jsonify({"loggedIn": True, **user})


@bp.route("/me", methods=["PATCH"])
def update_me():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "not logged in"}), 401
    data = request.get_json(silent=True) or {}
    user = update_user(user_id, data)
    if not user:
        return jsonify({"error": "user not found"}), 404
    return jsonify(user)


@bp.route("/change-password", methods=["POST"])
def change_password_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "not logged in"}), 401
    data = request.get_json(silent=True) or {}
    current_password = data.get("current_password") or ""
    new_password = data.get("new_password") or ""

    error = change_password(user_id, current_password, new_password)
    if error:
        status = 401 if "incorrect" in error.lower() else 400
        return jsonify({"error": error}), status
    return jsonify({"changed": True})
