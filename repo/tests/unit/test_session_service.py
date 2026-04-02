from datetime import datetime, timedelta, timezone

from flask import session

from app.services import session_service


def test_confirm_reauth_expires_after_five_minutes(app):
    with app.test_request_context("/"):
        action = "create_template"
        session_service.require_reauth(action)
        assert session_service.has_reauth_for(action) is False

        session_service.confirm_reauth(action)
        assert session_service.has_reauth_for(action) is True

        session["reauth_confirmed"][action] = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=6)).isoformat()
        assert session_service.has_reauth_for(action) is False


def test_confirm_reauth_invalid_timestamp_returns_false(app):
    with app.test_request_context("/"):
        action = "grant_user_permission"
        session["reauth_confirmed"] = {action: "not-a-timestamp"}
        assert session_service.has_reauth_for(action) is False
