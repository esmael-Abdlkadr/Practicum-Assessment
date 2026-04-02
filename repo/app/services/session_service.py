import os
from datetime import datetime, timedelta, timezone

from flask import current_app, session

from app.extensions import db
from app.models.user import User


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def login_user(user: User) -> None:
    now = _utcnow().isoformat()
    session.clear()
    session["user_id"] = user.id
    session["username"] = user.username
    session["role"] = user.role
    session["active_role"] = user.role
    session["logged_in_at"] = now
    session["last_active_at"] = now


def logout_user() -> None:
    session.clear()


def _session_lifetime() -> timedelta:
    """Return the configured session inactivity timeout.

    Reads ``PERMANENT_SESSION_LIFETIME`` from the Flask app config, which is
    set from the ``SESSION_LIFETIME_MINUTES`` environment variable in the app
    factory.  Falls back to 30 minutes when called outside an app context.
    """
    try:
        lifetime = current_app.config.get("PERMANENT_SESSION_LIFETIME")
        if isinstance(lifetime, timedelta):
            return lifetime
    except RuntimeError:
        pass
    minutes = int(os.environ.get("SESSION_LIFETIME_MINUTES", "30"))
    return timedelta(minutes=minutes)


def is_session_expired() -> bool:
    last_active = _parse_ts(session.get("last_active_at"))
    if not last_active:
        return False
    return last_active + _session_lifetime() < _utcnow()


def get_current_user() -> User | None:
    user_id = session.get("user_id")
    if not user_id:
        return None

    if is_session_expired():
        logout_user()
        return None

    user = db.session.get(User, user_id)
    if not user or not user.is_active:
        logout_user()
        return None

    return user


def refresh_activity() -> None:
    if session.get("user_id"):
        session["last_active_at"] = _utcnow().isoformat()


def require_reauth(action: str) -> None:
    """Mark this action as requiring re-auth."""
    reauth_map = session.get("reauth_confirmed", {})
    reauth_map.pop(action, None)
    session["reauth_confirmed"] = reauth_map
    session["reauth_required_for"] = action


def confirm_reauth(action: str) -> None:
    reauth_map = session.get("reauth_confirmed", {})
    reauth_map[action] = _utcnow().isoformat()
    session["reauth_confirmed"] = reauth_map


def set_reauth_verified(action: str) -> None:
    confirm_reauth(action)


def has_reauth_for(action: str) -> bool:
    reauth_map = session.get("reauth_confirmed", {})
    ts_str = reauth_map.get(action)
    if not ts_str:
        return False
    confirmed_at = _parse_ts(ts_str)
    if not confirmed_at:
        return False
    return _utcnow() - confirmed_at < timedelta(minutes=5)


def get_active_role() -> str | None:
    return session.get("active_role") or session.get("role")
