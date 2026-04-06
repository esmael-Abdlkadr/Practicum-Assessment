import random
import re
from datetime import datetime, timedelta, timezone

import bcrypt
from flask import session

from app.extensions import db
from app.models.login_attempt import LoginAttempt
from app.models.user import User
from app.services import audit_service


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def validate_password_strength(plain: str) -> tuple[bool, str]:
    if len(plain) < 12:
        return False, "Password must be at least 12 characters long."

    checks = [
        bool(re.search(r"[A-Z]", plain)),
        bool(re.search(r"[a-z]", plain)),
        bool(re.search(r"\d", plain)),
        bool(re.search(r"[^A-Za-z0-9]", plain)),
    ]

    if sum(checks) < 3:
        return False, "Password must contain at least 3 of: uppercase, lowercase, digit, special character."

    return True, ""


def get_failed_attempts_last_15min(username: str) -> int:
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=15)
    return (
        LoginAttempt.query.filter(
            LoginAttempt.username == username,
            LoginAttempt.success.is_(False),
            LoginAttempt.attempted_at >= cutoff,
        )
        .count()
    )


def is_account_locked(user: User) -> bool:
    return bool(user.locked_until and user.locked_until > datetime.now(timezone.utc).replace(tzinfo=None))


def lock_account(user: User) -> None:
    user.locked_until = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=15)
    db.session.add(user)
    db.session.commit()
    audit_service.log(
        action="ACCOUNT_LOCKED",
        resource_type="user",
        resource_id=user.id,
        extra={"username": user.username},
    )


def reset_failed_attempts(user: User) -> None:
    user.failed_attempts = 0
    user.locked_until = None
    db.session.add(user)
    db.session.commit()


def record_login_attempt(username: str, ip: str | None, success: bool) -> None:
    attempt = LoginAttempt(username=username, ip_address=ip, success=success)
    db.session.add(attempt)
    db.session.commit()


def authenticate(username: str, password: str, ip: str | None) -> tuple[User | None, str]:
    user = User.query.filter_by(username=username).first()
    if not user:
        record_login_attempt(username, ip, False)
        audit_service.log(action="LOGIN_FAILED", resource_type="user", extra={"username": username, "reason": "user_not_found"})
        return None, "Invalid username or password."

    if is_account_locked(user):
        record_login_attempt(username, ip, False)
        audit_service.log(
            action="LOGIN_FAILED",
            resource_type="user",
            resource_id=user.id,
            extra={"username": username, "reason": "account_locked"},
        )
        return None, "Account locked for 15 minutes."

    if not verify_password(password, user.password_hash):
        user.failed_attempts = (user.failed_attempts or 0) + 1
        db.session.add(user)

        if user.failed_attempts >= 8:
            lock_account(user)
            record_login_attempt(username, ip, False)
            audit_service.log(
                action="LOGIN_FAILED",
                resource_type="user",
                resource_id=user.id,
                extra={"username": username, "reason": "wrong_password_locked"},
            )
            return None, "Account locked for 15 minutes."

        db.session.commit()
        record_login_attempt(username, ip, False)
        audit_service.log(
            action="LOGIN_FAILED",
            resource_type="user",
            resource_id=user.id,
            extra={"username": username, "reason": "wrong_password"},
        )
        # Evaluate anomalies on failed login to catch brute-force patterns.
        audit_service.evaluate_user_anomalies(user.id, user.username)
        return None, "Invalid username or password."

    reset_failed_attempts(user)
    if user.mfa_enabled:
        session["mfa_pending_user_id"] = user.id
        session["pending_username"] = user.username
        return None, "mfa_required"

    user.last_login_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.session.add(user)
    db.session.commit()
    record_login_attempt(username, ip, True)
    audit_service.log(action="LOGIN_SUCCESS", resource_type="user", resource_id=user.id)
    # Incremental anomaly evaluation for this user only (no full-table scan).
    audit_service.evaluate_user_anomalies(user.id, user.username)
    return user, ""


def requires_captcha(username: str) -> bool:
    if not username:
        return False
    return get_failed_attempts_last_15min(username) >= 3


def generate_captcha() -> tuple[str, str]:
    a = random.randint(1, 9)
    b = random.randint(1, 9)
    return f"{a} + {b} = ?", str(a + b)


def verify_captcha(answer: str, expected: str) -> bool:
    return (answer or "").strip() == (expected or "").strip()
