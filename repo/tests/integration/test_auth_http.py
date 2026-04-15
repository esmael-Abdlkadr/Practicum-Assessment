"""Real HTTP auth tests — requests.Session against live Flask server.

No mocks, no monkeypatching: every test hits a real TCP socket.
"""
import requests
import pytest

from tests.integration.conftest import http_login


# ---------------------------------------------------------------------------
# 1. Login success sets session cookie
# ---------------------------------------------------------------------------

def test_login_success_sets_session_cookie(live_server, seeded):
    s = requests.Session()
    resp = s.post(
        f"{live_server}/login",
        data={"username": "h_admin", "password": "Admin@Practicum1"},
        allow_redirects=True,
    )
    assert resp.status_code == 200
    # At least one cookie must be set (session cookie)
    assert len(s.cookies) > 0, "No cookies set after successful login"
    s.close()


# ---------------------------------------------------------------------------
# 2. Login invalid returns error fragment
# ---------------------------------------------------------------------------

def test_login_invalid_returns_error_fragment(live_server, seeded):
    s = requests.Session()
    resp = s.post(
        f"{live_server}/login",
        data={"username": "h_admin", "password": "WrongPassword1!"},
        allow_redirects=True,
    )
    assert resp.status_code == 200
    assert "invalid" in resp.text.lower() or "incorrect" in resp.text.lower(), (
        f"Expected error text not found in: {resp.text[:300]}"
    )
    s.close()


# ---------------------------------------------------------------------------
# 3. Login redirect after success lands on /dashboard or /change-password
# ---------------------------------------------------------------------------

def test_login_redirect_after_success(live_server, seeded):
    s = requests.Session()
    resp = s.post(
        f"{live_server}/login",
        data={"username": "h_admin", "password": "Admin@Practicum1"},
        allow_redirects=True,
    )
    assert resp.status_code == 200
    # Must have landed on dashboard or change-password
    assert "/dashboard" in resp.url or "/change-password" in resp.url, (
        f"Unexpected final URL after login: {resp.url}"
    )
    s.close()


# ---------------------------------------------------------------------------
# 4. Logout clears session — subsequent /dashboard returns 302 to /login
# ---------------------------------------------------------------------------

def test_logout_clears_session(live_server, seeded):
    s = requests.Session()
    # Login first
    http_login(s, live_server, "h_admin", "Admin@Practicum1")
    # Logout
    s.get(f"{live_server}/logout", allow_redirects=True)
    # Dashboard should redirect to login now
    resp = s.get(f"{live_server}/dashboard", allow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("Location", ""), (
        f"Expected redirect to /login after logout, got Location: {resp.headers.get('Location')}"
    )
    s.close()


# ---------------------------------------------------------------------------
# 5. Reauth gate on high-risk endpoint (PUT /admin/users/<id>)
# ---------------------------------------------------------------------------

def test_reauth_gate_on_high_risk_endpoint(live_server, seeded):
    s = requests.Session()
    http_login(s, live_server, "h_admin", "Admin@Practicum1")
    admin_id = seeded["admin_id"]
    # PUT /admin/users/<id> is decorated with @high_risk_action → should redirect to /reauth
    resp = s.put(
        f"{live_server}/admin/users/{admin_id}",
        data={"full_name": "Test Name"},
        allow_redirects=False,
    )
    assert resp.status_code == 302, (
        f"Expected 302 redirect for unauthenticated high-risk action, got {resp.status_code}"
    )
    location = resp.headers.get("Location", "")
    assert "/reauth" in location, (
        f"Expected redirect to /reauth, got Location: {location}"
    )
    s.close()


# ---------------------------------------------------------------------------
# 6. Reauth completes and allows high-risk action
# ---------------------------------------------------------------------------

def test_reauth_completes_and_allows_action(live_server, seeded):
    s = requests.Session()
    http_login(s, live_server, "h_admin", "Admin@Practicum1")
    admin_id = seeded["admin_id"]
    target_url = f"/admin/users/{admin_id}"

    # Trigger reauth gate — stores action in session
    s.put(f"{live_server}{target_url}", data={"full_name": "Pending"}, allow_redirects=False)

    # Complete reauth
    s.post(
        f"{live_server}/reauth",
        data={"password": "Admin@Practicum1", "next_url": target_url},
        allow_redirects=True,
    )

    # Retry the PUT — should now succeed (200 or 302 to non-reauth)
    resp = s.put(
        f"{live_server}{target_url}",
        data={"full_name": "Updated Name"},
        allow_redirects=False,
    )
    assert resp.status_code not in (301, 302) or "/reauth" not in resp.headers.get("Location", ""), (
        "PUT still redirecting to /reauth after completing reauth"
    )
    # Accept 200 (HTMX fragment) or 302 to non-reauth destination
    assert resp.status_code in (200, 302, 204), (
        f"Unexpected status after reauth: {resp.status_code}"
    )
    s.close()


# ---------------------------------------------------------------------------
# 7. POST /switch-role without reauth redirects to /reauth
# ---------------------------------------------------------------------------

def test_switch_role_requires_reauth(live_server, seeded):
    s = requests.Session()
    http_login(s, live_server, "h_admin", "Admin@Practicum1")
    resp = s.post(
        f"{live_server}/switch-role",
        data={"role": "faculty_advisor"},
        allow_redirects=False,
    )
    assert resp.status_code == 302, (
        f"Expected 302 redirect for switch-role without reauth, got {resp.status_code}"
    )
    assert "/reauth" in resp.headers.get("Location", ""), (
        f"Expected redirect to /reauth for switch-role, got: {resp.headers.get('Location')}"
    )
    s.close()


# ---------------------------------------------------------------------------
# 8. Switch-role completes after reauth
# ---------------------------------------------------------------------------

def test_switch_role_completes_after_reauth(live_server, seeded, http_app):
    from app.extensions import db
    from app.models.permission import UserPermission

    # Grant the admin user permission to switch to faculty_advisor
    with http_app.app_context():
        admin_id = seeded["admin_id"]
        existing = UserPermission.query.filter_by(
            user_id=admin_id, permission="role:faculty_advisor"
        ).first()
        if not existing:
            db.session.add(UserPermission(user_id=admin_id, permission="role:faculty_advisor"))
            db.session.commit()

    s = requests.Session()
    http_login(s, live_server, "h_admin", "Admin@Practicum1")

    # Trigger switch-role → reauth redirect (action stored in session)
    s.post(
        f"{live_server}/switch-role",
        data={"role": "faculty_advisor"},
        allow_redirects=False,
    )

    # Complete reauth
    s.post(
        f"{live_server}/reauth",
        data={"password": "Admin@Practicum1", "next_url": "/switch-role"},
        allow_redirects=True,
    )

    # Retry switch-role — should succeed now
    resp = s.post(
        f"{live_server}/switch-role",
        data={"role": "faculty_advisor"},
        allow_redirects=False,
    )
    # 302 to dashboard / 204 = success; NOT a redirect back to /reauth
    assert resp.status_code in (302, 204), (
        f"Unexpected status after reauth + switch-role: {resp.status_code}"
    )
    if resp.status_code == 302:
        assert "/reauth" not in resp.headers.get("Location", ""), (
            "Still redirecting to /reauth after completing reauth"
        )
    s.close()


# ---------------------------------------------------------------------------
# 9. Unauthenticated GET /dashboard redirects to /login
# ---------------------------------------------------------------------------

def test_unauthenticated_redirects_to_login(live_server, seeded):
    s = requests.Session()
    resp = s.get(f"{live_server}/dashboard", allow_redirects=False)
    assert resp.status_code == 302, (
        f"Expected 302 for unauthenticated /dashboard, got {resp.status_code}"
    )
    assert "/login" in resp.headers.get("Location", ""), (
        f"Expected redirect to /login, got: {resp.headers.get('Location')}"
    )
    s.close()


# ---------------------------------------------------------------------------
# 10. MFA setup page requires login
# ---------------------------------------------------------------------------

def test_mfa_setup_page_requires_login(live_server, seeded):
    s = requests.Session()
    resp = s.get(f"{live_server}/settings/mfa", allow_redirects=False)
    assert resp.status_code == 302, (
        f"Expected 302 for unauthenticated /settings/mfa, got {resp.status_code}"
    )
    assert "/login" in resp.headers.get("Location", ""), (
        f"Expected redirect to /login, got: {resp.headers.get('Location')}"
    )
    s.close()
