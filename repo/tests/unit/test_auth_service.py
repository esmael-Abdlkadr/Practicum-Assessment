from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models.login_attempt import LoginAttempt
from app.models.user import User
from app.services.auth_service import authenticate, is_account_locked, requires_captcha


def test_authenticate_success(app, admin_user):
    with app.app_context():
        user, error = authenticate("admin", "Admin@Practicum1", "127.0.0.1")
        assert user is not None
        assert error == ""


def test_authenticate_wrong_password_increments_failed_attempts(app, admin_user):
    with app.app_context():
        user = User.query.filter_by(username="admin").first()
        user.failed_attempts = 0
        db.session.add(user)
        db.session.commit()

        out, _ = authenticate("admin", "Wrong@Pass123", "127.0.0.1")
        assert out is None

        user = User.query.filter_by(username="admin").first()
        assert user.failed_attempts == 1


def test_authenticate_locked_account_returns_immediate_error(app, admin_user):
    with app.app_context():
        user = User.query.filter_by(username="admin").first()
        user.locked_until = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=5)
        db.session.add(user)
        db.session.commit()

        out, err = authenticate("admin", "Admin@Practicum1", "127.0.0.1")
        assert out is None
        assert "Account locked" in err


def test_is_account_locked_past_time_false(app, admin_user):
    with app.app_context():
        user = User.query.filter_by(username="admin").first()
        user.locked_until = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
        db.session.add(user)
        db.session.commit()
        assert is_account_locked(user) is False


def test_requires_captcha_after_three_failed_attempts(app, admin_user):
    with app.app_context():
        db.session.query(LoginAttempt).delete()
        for _ in range(3):
            db.session.add(LoginAttempt(username="admin", ip_address="127.0.0.1", success=False))
        db.session.commit()
        assert requires_captcha("admin") is True


def test_authenticate_unknown_user_returns_invalid(app):
    with app.app_context():
        out, err = authenticate("unknown", "Whatever@1234", "127.0.0.1")
        assert out is None
        assert "Invalid username or password" in err


def test_requires_captcha_false_with_no_username(app):
    with app.app_context():
        assert requires_captcha("") is False
