"""JSON-backed user accounts; passwords hashed via werkzeug."""

import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from werkzeug.security import check_password_hash, generate_password_hash

from app.config import settings

_USERS_FILE = os.path.join(settings.EMBEDDING_DIR, "..", "users.json")
_USERS_FILE = os.path.normpath(_USERS_FILE)


def _ensure_dir() -> None:
    d = os.path.dirname(_USERS_FILE)
    os.makedirs(d, exist_ok=True)


def _load() -> List[Dict]:
    _ensure_dir()
    if not os.path.exists(_USERS_FILE):
        return []
    try:
        with open(_USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save(users: List[Dict]) -> None:
    _ensure_dir()
    with open(_USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)


def _public(user: Dict) -> Dict:
    """Strip the password hash; compute is_admin (stored flag or email in ADMIN_EMAILS) fresh each read."""
    result = {k: v for k, v in user.items() if k != "password_hash"}
    result["is_admin"] = bool(user.get("is_admin")) or (
        user.get("email", "").strip().lower() in settings.ADMIN_EMAILS
    )
    return result


def validate_password_strength(password: str) -> Optional[str]:
    """Error message if the password is too weak, else None."""
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if not re.search(r"[a-z]", password):
        return "Password must include at least one lowercase letter."
    if not re.search(r"[A-Z]", password):
        return "Password must include at least one uppercase letter."
    if not re.search(r"\d", password):
        return "Password must include at least one number."
    if not re.search(r"[^a-zA-Z0-9]", password):
        return "Password must include at least one special character."
    return None


def find_by_username_or_email(identifier: str) -> Optional[Dict]:
    identifier = identifier.strip().lower()
    for u in _load():
        if u["username"].lower() == identifier or u["email"].lower() == identifier:
            return u
    return None


def create_user(username: str, email: str, password: str) -> Dict:
    users = _load()
    if find_by_username_or_email(username) or find_by_username_or_email(email):
        raise ValueError("A user with that username or email already exists.")

    weakness = validate_password_strength(password)
    if weakness:
        raise ValueError(weakness)

    user = {
        "id": uuid.uuid4().hex[:12],
        "username": username.strip(),
        "email": email.strip(),
        "password_hash": generate_password_hash(password),
        "display_name": username.strip(),
        "default_voice": "",
        "is_admin": len(users) == 0,  # first user is admin
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    users.append(user)
    _save(users)
    return _public(user)


def authenticate(identifier: str, password: str) -> Optional[Dict]:
    user = find_by_username_or_email(identifier)
    if user and check_password_hash(user["password_hash"], password):
        return _public(user)
    return None


def get_user(user_id: str) -> Optional[Dict]:
    for u in _load():
        if u["id"] == user_id:
            return _public(u)
    return None


def list_users() -> List[Dict]:
    return [_public(u) for u in _load()]


def update_user(user_id: str, fields: Dict) -> Optional[Dict]:
    """Only display_name and default_voice can be updated here."""
    allowed = {"display_name", "default_voice"}
    users = _load()
    for u in users:
        if u["id"] == user_id:
            for k, v in fields.items():
                if k in allowed:
                    u[k] = v
            _save(users)
            return _public(u)
    return None


def change_password(user_id: str, current_password: str, new_password: str) -> Optional[str]:
    """None on success, else an error message string."""
    weakness = validate_password_strength(new_password)
    if weakness:
        return weakness

    users = _load()
    for u in users:
        if u["id"] == user_id:
            if not check_password_hash(u["password_hash"], current_password):
                return "Current password is incorrect."
            u["password_hash"] = generate_password_hash(new_password)
            _save(users)
            return None
    return "User not found."
