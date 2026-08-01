"""Small helper so every route that needs "whose data is this" doesn't
repeat the same session-lookup-with-guest-fallback logic. Not logging in at
all still works — everything just lands in a shared 'guest' bucket, same
behavior as before Phase 4, so nothing breaks for someone who doesn't want
to create an account.
"""

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
