"""Current-user lookup with a shared 'guest' fallback."""

from typing import Optional

from flask import session

from app.auth.users_store import get_user


def current_user_id() -> str:
    return session.get("user_id") or "guest"


def current_user() -> Optional[dict]:
    user_id = session.get("user_id")
    if not user_id:
        return None
    return get_user(user_id)


def is_admin() -> bool:
    user = current_user()
    return bool(user and user.get("is_admin"))
