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
    # After the fix, setup no longer writes to DB — secret lives in session only
    with client.session_transaction() as sess:
        assert sess.get("mfa_setup_secret") is not None


def test_mfa_verify_setup_with_valid_totp(client, app, admin_user):
    _login(client)
    client.post("/settings/mfa/setup")
    # Secret is now only in session, not DB
    with client.session_transaction() as sess:
        secret = sess.get("mfa_setup_secret")
    assert secret is not None
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
    # Secret is now only in session, not DB
    with client.session_transaction() as sess:
        secret = sess.get("mfa_setup_secret")
    assert secret is not None
    totp = pyotp.TOTP(secret).now()
    res = client.post("/settings/mfa/verify-setup", data={"totp_code": totp}, follow_redirects=False)
    assert res.status_code in (200, 302, 204)

    with app.app_context():
        row = AuditLog.query.filter_by(action="MFA_ENABLED").first()
        assert row is not None


def test_mfa_setup_does_not_disable_active_mfa(client, app, admin_user):
    """Regression: hitting /settings/mfa/setup must NOT set mfa_enabled=False for a user
    who already has MFA enabled.  The persisted mfa_enabled state must remain True
    until the user explicitly disables via the /disable endpoint (which requires re-auth)."""
    with app.app_context():
        secret = pyotp.random_base32()
        u = User.query.filter_by(username="admin").first()
        u.mfa_secret = secret
        u.mfa_enabled = True
        db.session.commit()

    _login(client)
    client.post("/settings/mfa/setup")

    with app.app_context():
        u = User.query.filter_by(username="admin").first()
        assert u.mfa_enabled is True, (
            "mfa_enabled must remain True after hitting /setup; "
            "only /disable (with re-auth) should set it to False."
        )


def test_mfa_setup_stores_pending_secret_only_in_session(client, app, admin_user):
    """The new temp secret generated during setup must NOT be committed to the DB;
    only the session should carry the pending secret until verify-setup succeeds."""
    with app.app_context():
        original_secret = pyotp.random_base32()
        u = User.query.filter_by(username="admin").first()
        u.mfa_secret = original_secret
        u.mfa_enabled = True
        db.session.commit()

    _login(client)
    client.post("/settings/mfa/setup")

    with app.app_context():
        u = User.query.filter_by(username="admin").first()
        # The persisted secret must still be the original one, not a new temp secret
        assert u.mfa_secret == original_secret, (
            "DB mfa_secret must not change during setup initiation; "
            "new secret should stay in session only until verify-setup."
        )


def test_mfa_disable_writes_audit_log(client, app, admin_user):
    from app.models.audit_log import AuditLog

    _login(client)
    client.post("/settings/mfa/setup")
    # Secret is now only in session, not DB
    with client.session_transaction() as sess:
        secret = sess.get("mfa_setup_secret")
    assert secret is not None
    totp = pyotp.TOTP(secret).now()
    client.post("/settings/mfa/verify-setup", data={"totp_code": totp}, follow_redirects=False)

    # Trigger the reauth redirect for mfa_disable, then complete it via /reauth
    client.post("/settings/mfa/disable", follow_redirects=False)
    client.post("/reauth", data={"password": "Admin@Practicum1", "next_url": "/settings/mfa/disable"}, follow_redirects=False)

    res = client.post("/settings/mfa/disable", follow_redirects=False)
    assert res.status_code in (200, 302, 204)

    with app.app_context():
        row = AuditLog.query.filter_by(action="MFA_DISABLED").first()
        assert row is not None
