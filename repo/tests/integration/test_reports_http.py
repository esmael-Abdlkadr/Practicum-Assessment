"""Real HTTP reports tests — requests.Session against live Flask server.

No mocks, no monkeypatching: every test hits a real TCP socket.
"""
import requests
import pytest

from tests.integration.conftest import http_login


# ---------------------------------------------------------------------------
# 1. GET /reports unauthenticated → 302 /login
# ---------------------------------------------------------------------------

def test_reports_index_requires_auth(live_server, seeded):
    s = requests.Session()
    resp = s.get(f"{live_server}/reports", allow_redirects=False)
    assert resp.status_code == 302, (
        f"Expected 302 redirect for unauthenticated /reports, got {resp.status_code}"
    )
    assert "/login" in resp.headers.get("Location", ""), (
        f"Expected redirect to /login, got: {resp.headers.get('Location')}"
    )
    s.close()


# ---------------------------------------------------------------------------
# 2. GET /reports accessible as admin → 200
# ---------------------------------------------------------------------------

def test_reports_index_accessible_as_admin(live_server, seeded):
    s = requests.Session()
    http_login(s, live_server, "h_admin", "Admin@Practicum1")
    resp = s.get(f"{live_server}/reports", allow_redirects=True)
    assert resp.status_code == 200, (
        f"Expected 200 for admin /reports, got {resp.status_code}. Body: {resp.text[:200]}"
    )
    s.close()


# ---------------------------------------------------------------------------
# 3. GET /reports/paper/<paper_id> accessible as admin → 200
# ---------------------------------------------------------------------------

def test_reports_paper_accessible_as_admin(live_server, seeded):
    s = requests.Session()
    http_login(s, live_server, "h_admin", "Admin@Practicum1")
    paper_id = seeded["paper_id"]
    resp = s.get(f"{live_server}/reports/paper/{paper_id}", allow_redirects=True)
    assert resp.status_code == 200, (
        f"Expected 200 for admin /reports/paper/{paper_id}, got {resp.status_code}"
    )
    s.close()


# ---------------------------------------------------------------------------
# 4. GET /reports/paper/<paper_id> forbidden for student → 302 or 403
# ---------------------------------------------------------------------------

def test_reports_paper_forbidden_for_student(live_server, seeded):
    s = requests.Session()
    http_login(s, live_server, "h_student", "Student@Practicum1")
    paper_id = seeded["paper_id"]
    resp = s.get(f"{live_server}/reports/paper/{paper_id}", allow_redirects=False)
    # Student role is not in the require_role list for reports → 302 or 403
    assert resp.status_code in (302, 403), (
        f"Expected 302 or 403 for student /reports/paper/{paper_id}, got {resp.status_code}"
    )
    s.close()


# ---------------------------------------------------------------------------
# 5. Export summary requires report:export permission
#    Advisor without permission → 403
# ---------------------------------------------------------------------------

def test_export_summary_requires_permission(live_server, seeded, http_app):
    from app.extensions import db
    from app.models.permission import UserPermission

    # Ensure advisor has NO report:export permission
    with http_app.app_context():
        advisor_id = seeded["advisor_id"]
        UserPermission.query.filter_by(
            user_id=advisor_id, permission="report:export"
        ).delete()
        db.session.commit()

    s = requests.Session()
    http_login(s, live_server, "h_advisor", "Advisor@Practicum1")
    paper_id = seeded["paper_id"]
    resp = s.get(
        f"{live_server}/reports/paper/{paper_id}/export/summary",
        allow_redirects=False,
    )
    assert resp.status_code == 403, (
        f"Expected 403 for advisor without report:export, got {resp.status_code}"
    )
    s.close()


# ---------------------------------------------------------------------------
# 6. Export summary with report:export permission → 200, Content-Disposition attachment
# ---------------------------------------------------------------------------

def test_export_summary_with_permission(live_server, seeded, http_app):
    from app.extensions import db
    from app.models.permission import UserPermission

    # Grant report:export to advisor
    with http_app.app_context():
        advisor_id = seeded["advisor_id"]
        existing = UserPermission.query.filter_by(
            user_id=advisor_id, permission="report:export"
        ).first()
        if not existing:
            db.session.add(UserPermission(user_id=advisor_id, permission="report:export"))
            db.session.commit()

    s = requests.Session()
    http_login(s, live_server, "h_advisor", "Advisor@Practicum1")
    paper_id = seeded["paper_id"]
    resp = s.get(
        f"{live_server}/reports/paper/{paper_id}/export/summary",
        allow_redirects=True,
    )
    assert resp.status_code == 200, (
        f"Expected 200 for advisor with report:export on export/summary, got {resp.status_code}"
    )
    content_disp = resp.headers.get("Content-Disposition", "")
    assert "attachment" in content_disp, (
        f"Expected Content-Disposition: attachment, got: {content_disp!r}"
    )
    s.close()
