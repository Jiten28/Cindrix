"""User account storage — JSON-based, consistent with the rest of the
project's file storage (see Memory.md's architecture decisions). Passwords
are hashed with werkzeug's built-in helpers (already a Flask dependency, no
new library needed).

The first user ever created is automatically flagged as admin — simplest
possible bootstrap for the admin panel without a separate setup step.
"""

import json
import os
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
    """Strips the password hash before returning a user to the frontend."""
    return {k: v for k, v in user.items() if k != "password_hash"}


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
    """Allows updating display_name and default_voice only — anything else
    (email, username, is_admin) needs a more deliberate path than a generic
    profile-update endpoint."""
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


def change_password(user_id: str, current_password: str, new_password: str) -> bool:
    users = _load()
    for u in users:
        if u["id"] == user_id:
            if not check_password_hash(u["password_hash"], current_password):
                return False
            u["password_hash"] = generate_password_hash(new_password)
            _save(users)
            return True
    return False
