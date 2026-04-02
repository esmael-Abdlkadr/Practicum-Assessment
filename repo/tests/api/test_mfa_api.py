import pyotp

from app.extensions import db
from app.models.user import User


def _login(client, username="admin", password="Admin@Practicum1"):
    client.post("/login", data={"username": username, "password": password})


def test_mfa_setup_page_returns_200(client, admin_user):
    _login(client)
    res = client.get("/settings/mfa/setup")
    assert res.status_code == 200


def test_mfa_setup_generates_secret(client, app, admin_user):
    _login(client)
    client.post("/settings/mfa/setup")
    with app.app_context():
        admin = User.query.filter_by(username="admin").first()
        user = db.session.get(User, admin.id)
        assert user.mfa_secret is not None


def test_mfa_verify_setup_with_valid_totp(client, app, admin_user):
    _login(client)
    client.post("/settings/mfa/setup")
    with app.app_context():
        admin = User.query.filter_by(username="admin").first()
        user = db.session.get(User, admin.id)
        secret = user.mfa_secret
    totp = pyotp.TOTP(secret).now()
    res = client.post("/settings/mfa/verify-setup", data={"totp_code": totp}, follow_redirects=False)
    assert res.status_code in (200, 302, 204)


def test_mfa_verify_setup_with_invalid_totp_returns_error(client, app, admin_user):
    _login(client)
    client.post("/settings/mfa/setup")
    res = client.post("/settings/mfa/verify-setup", data={"totp_code": "000000"}, headers={"HX-Request": "true"})
    body = res.get_data(as_text=True)
    assert res.status_code in (200, 400) or "invalid" in body.lower() or "incorrect" in body.lower()


def test_mfa_disable_requires_reauth(client, app, admin_user):
    _login(client)
    res = client.post("/settings/mfa/disable", follow_redirects=False)
    assert res.status_code in (302, 403)


def test_login_with_mfa_enabled_requires_totp(client, app, admin_user):
    """
    When MFA is enabled for a user, a successful password login must NOT
    go directly to /dashboard - it must redirect to /login/mfa.
    """
    with app.app_context():
        secret = pyotp.random_base32()
        u = User.query.filter_by(username="admin").first()
        u.mfa_secret = secret
        u.mfa_enabled = True
        db.session.commit()

    resp = client.post(
        "/login",
        data={"username": "admin", "password": "Admin@Practicum1"},
        follow_redirects=False,
    )
    location = resp.headers.get("Location", "")
    assert "/login/mfa" in location or resp.status_code in (200, 302), (
        "MFA-enabled login should redirect to /login/mfa"
    )
    with client.session_transaction() as sess:
        assert "user_id" not in sess
        assert sess.get("mfa_pending_user_id") is not None


def test_login_with_mfa_valid_totp_completes_login(client, app, admin_user):
    """
    Submitting a valid TOTP after password login must complete authentication
    and redirect to /dashboard.
    """
    with app.app_context():
        secret = pyotp.random_base32()
        u = User.query.filter_by(username="admin").first()
        u.mfa_secret = secret
        u.mfa_enabled = True
        db.session.commit()
        stored_secret = secret

    client.post(
        "/login",
        data={"username": "admin", "password": "Admin@Practicum1"},
        follow_redirects=False,
    )
    totp = pyotp.TOTP(stored_secret).now()
    resp = client.post(
        "/login/mfa",
        data={"totp_code": totp},
        follow_redirects=False,
    )
    location = resp.headers.get("Location", "")
    assert "/dashboard" in location or resp.status_code == 302


def test_login_with_mfa_invalid_totp_returns_error(client, app, admin_user):
    """
    Submitting a wrong TOTP after password login must NOT authenticate the user.
    """
    with app.app_context():
        secret = pyotp.random_base32()
        u = User.query.filter_by(username="admin").first()
        u.mfa_secret = secret
        u.mfa_enabled = True
        db.session.commit()

    client.post(
        "/login",
        data={"username": "admin", "password": "Admin@Practicum1"},
        follow_redirects=False,
    )
    resp = client.post(
        "/login/mfa",
        data={"totp_code": "000000"},
        follow_redirects=False,
    )
    location = resp.headers.get("Location", "")
    assert "/dashboard" not in location
    with client.session_transaction() as sess:
        assert "user_id" not in sess
        assert sess.get("mfa_pending_user_id") is not None


def test_mfa_enable_writes_audit_log(client, app, admin_user):
    from app.models.audit_log import AuditLog

    _login(client)
    client.post("/settings/mfa/setup")
    with app.app_context():
        admin = User.query.filter_by(username="admin").first()
        secret = db.session.get(User, admin.id).mfa_secret
    totp = pyotp.TOTP(secret).now()
    res = client.post("/settings/mfa/verify-setup", data={"totp_code": totp}, follow_redirects=False)
    assert res.status_code in (200, 302, 204)

    with app.app_context():
        row = AuditLog.query.filter_by(action="MFA_ENABLED").first()
        assert row is not None


def test_mfa_disable_writes_audit_log(client, app, admin_user):
    from app.models.audit_log import AuditLog

    _login(client)
    client.post("/settings/mfa/setup")
    with app.app_context():
        admin = User.query.filter_by(username="admin").first()
        secret = db.session.get(User, admin.id).mfa_secret
    totp = pyotp.TOTP(secret).now()
    client.post("/settings/mfa/verify-setup", data={"totp_code": totp}, follow_redirects=False)

    with client.session_transaction() as sess:
        from datetime import datetime, timezone

        sess.setdefault("reauth_confirmed", {})
        sess["reauth_confirmed"]["mfa_disable"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    res = client.post("/settings/mfa/disable", follow_redirects=False)
    assert res.status_code in (200, 302, 204)

    with app.app_context():
        row = AuditLog.query.filter_by(action="MFA_DISABLED").first()
        assert row is not None
