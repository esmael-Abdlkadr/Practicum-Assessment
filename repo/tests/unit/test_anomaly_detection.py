"""Unit tests for anomaly detection logic in audit_service."""
from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.user import User
from app.services import audit_service
from app.services.auth_service import hash_password


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _make_user(app, username="testuser"):
    with app.app_context():
        user = User.query.filter_by(username=username).first()
        if not user:
            user = User(
                username=username,
                role="student",
                password_hash=hash_password("Student@Practicum1"),
                is_active=True,
            )
            db.session.add(user)
            db.session.commit()
        return user.id


def _add_log(app, user_id, action, created_at=None, device_fingerprint="fp-default", ip_address="127.0.0.1"):
    with app.app_context():
        entry = AuditLog(
            actor_id=user_id,
            actor_username="testuser",
            action=action,
            ip_address=ip_address,
            device_fingerprint=device_fingerprint,
            resource_type=None,
            resource_id=None,
        )
        if created_at:
            entry.created_at = created_at
        db.session.add(entry)
        db.session.commit()


def test_no_anomalies_for_clean_user(app):
    uid = _make_user(app, "cleanuser")
    # One successful login from a known device on a normal hour (10 AM)
    ts = _utcnow().replace(hour=10, minute=0, second=0, microsecond=0)
    _add_log(app, uid, "LOGIN_SUCCESS", created_at=ts)
    # Add a second login with the same fingerprint so it's not "new"
    _add_log(app, uid, "LOGIN_SUCCESS", created_at=ts - timedelta(days=1))

    with app.app_context():
        anomalies = audit_service.detect_anomalies(uid)
    assert anomalies == []


def test_brute_force_flag_when_over_5_failures_in_1h(app):
    uid = _make_user(app, "bruteuser")
    now = _utcnow()
    for _ in range(6):
        _add_log(app, uid, "LOGIN_FAILED", created_at=now - timedelta(minutes=10))

    with app.app_context():
        anomalies = audit_service.detect_anomalies(uid)
    assert any("failed login" in a.lower() for a in anomalies)


def test_no_brute_force_with_5_or_fewer_failures(app):
    uid = _make_user(app, "okuser")
    now = _utcnow()
    for _ in range(5):
        _add_log(app, uid, "LOGIN_FAILED", created_at=now - timedelta(minutes=10))

    with app.app_context():
        anomalies = audit_service.detect_anomalies(uid)
    assert not any("failed login" in a.lower() for a in anomalies)


def test_unusual_hour_flag_midnight_login(app):
    uid = _make_user(app, "nightuser")
    # Login at 2 AM (unusual: < 6 or >= 23)
    ts = _utcnow().replace(hour=2, minute=0, second=0, microsecond=0)
    _add_log(app, uid, "LOGIN_SUCCESS", created_at=ts)

    with app.app_context():
        anomalies = audit_service.detect_anomalies(uid)
    assert any("unusual hour" in a.lower() for a in anomalies)


def test_unusual_hour_flag_late_night_login(app):
    uid = _make_user(app, "lateuser")
    ts = _utcnow().replace(hour=23, minute=30, second=0, microsecond=0)
    _add_log(app, uid, "LOGIN_SUCCESS", created_at=ts)

    with app.app_context():
        anomalies = audit_service.detect_anomalies(uid)
    assert any("unusual hour" in a.lower() for a in anomalies)


def test_normal_hour_no_unusual_hour_flag(app):
    uid = _make_user(app, "dayuser")
    ts = _utcnow().replace(hour=9, minute=0, second=0, microsecond=0)
    # Two logins with same device so "new device" doesn't fire
    _add_log(app, uid, "LOGIN_SUCCESS", created_at=ts, device_fingerprint="day-fp")
    _add_log(app, uid, "LOGIN_SUCCESS", created_at=ts - timedelta(days=1), device_fingerprint="day-fp")

    with app.app_context():
        anomalies = audit_service.detect_anomalies(uid)
    assert not any("unusual hour" in a.lower() for a in anomalies)


def test_new_device_fingerprint_flagged(app):
    uid = _make_user(app, "newdeviceuser")
    now = _utcnow().replace(hour=10)
    # Only one login from this fingerprint — should flag as new device
    _add_log(app, uid, "LOGIN_SUCCESS", created_at=now, device_fingerprint="brand-new-fp")

    with app.app_context():
        anomalies = audit_service.detect_anomalies(uid)
    assert any("new device" in a.lower() for a in anomalies)


def test_multiple_ips_in_24h_flagged(app):
    uid = _make_user(app, "multiipuser")
    now = _utcnow().replace(hour=10)
    ips = ["10.0.0.1", "10.0.0.2", "10.0.0.3", "10.0.0.4"]
    for ip in ips:
        _add_log(app, uid, "LOGIN_SUCCESS", created_at=now - timedelta(hours=1), ip_address=ip)

    with app.app_context():
        anomalies = audit_service.detect_anomalies(uid)
    assert any("ip" in a.lower() for a in anomalies)


def test_three_or_fewer_ips_not_flagged(app):
    uid = _make_user(app, "fewipuser")
    now = _utcnow().replace(hour=10)
    ips = ["10.1.1.1", "10.1.1.2", "10.1.1.3"]
    for ip in ips:
        _add_log(app, uid, "LOGIN_SUCCESS", created_at=now - timedelta(hours=1), ip_address=ip)

    with app.app_context():
        anomalies = audit_service.detect_anomalies(uid)
    assert not any("ip" in a.lower() for a in anomalies)


def test_detect_anomalies_no_logs_returns_empty(app):
    uid = _make_user(app, "emptylogs")
    with app.app_context():
        anomalies = audit_service.detect_anomalies(uid)
    assert anomalies == []
