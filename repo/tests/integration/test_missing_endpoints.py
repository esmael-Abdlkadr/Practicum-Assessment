"""Real HTTP tests for missing/uncovered endpoints.

Each test spins up a real requests.Session against the live Flask server.
No mocks, no Flask test client.

Routes confirmed present via grep on app/routes/:
  - GET /admin/assignments            (assignments.py)
  - GET /admin/assignments/new        (assignments.py)
  - GET /login/mfa                    (auth.py)
  - GET /reauth                       (auth.py)
  - GET /change-password              (auth.py)
  - GET /settings/mfa                 (mfa.py, prefix /settings/mfa, route "")
  - GET /grading/paper/<id>           (grading.py)
  - GET /                             (main.py)
  - GET /admin/org/cohorts/<id>/members (org.py)
  - GET /admin/papers/new             (papers.py)
  - PUT /admin/papers/<id>/questions/reorder (papers.py)
  - GET /admin/permissions/templates  (permissions.py)
  - POST /admin/permissions/grant     (permissions.py, @high_risk_action)
  - GET /admin/permissions/delegations (permissions.py)
  - GET /admin/questions/<id>/edit    (questions.py)
  - GET /reports/paper/<id>/export/summary (reports.py, @permission_required)
  - POST /quiz/<id>/start max-attempts (quiz.py)
"""
import requests
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _login(live_server, username, password):
    s = requests.Session()
    s.post(
        f"{live_server}/login",
        data={"username": username, "password": password},
        allow_redirects=True,
    )
    return s


def _do_reauth(s, live_server, password, action_url=None):
    """Trigger reauth gate then confirm it so @high_risk_action passes."""
    if action_url:
        # Trigger the gate (stores action in session, redirects to /reauth)
        s.get(f"{live_server}{action_url}", allow_redirects=False)
    s.post(
        f"{live_server}/reauth",
        data={"password": password, "next_url": action_url or "/dashboard"},
        allow_redirects=True,
    )


# ---------------------------------------------------------------------------
# Admin/Assignments
# ---------------------------------------------------------------------------

def test_admin_assignments_list_admin_200(live_server, seeded, http_app):
    """GET /admin/assignments → admin 200."""
    s = _login(live_server, "h_admin", "Admin@Practicum1")
    resp = s.get(f"{live_server}/admin/assignments", allow_redirects=True)
    assert resp.status_code == 200, f"Expected 200 got {resp.status_code}: {resp.text[:200]}"
    s.close()


def test_admin_assignments_list_student_403(live_server, seeded, http_app):
    """GET /admin/assignments → student gets 403."""
    s = _login(live_server, "h_student", "Student@Practicum1")
    resp = s.get(f"{live_server}/admin/assignments", allow_redirects=True)
    assert resp.status_code == 403, f"Expected 403 got {resp.status_code}: {resp.text[:200]}"
    s.close()


def test_admin_assignments_new_admin_200(live_server, seeded, http_app):
    """GET /admin/assignments/new → admin 200."""
    s = _login(live_server, "h_admin", "Admin@Practicum1")
    resp = s.get(f"{live_server}/admin/assignments/new", allow_redirects=True)
    assert resp.status_code == 200, f"Expected 200 got {resp.status_code}: {resp.text[:200]}"
    s.close()


# ---------------------------------------------------------------------------
# Auth flows
# ---------------------------------------------------------------------------

def test_login_mfa_unauthenticated_redirects_to_login(live_server, seeded, http_app):
    """GET /login/mfa without mfa_pending_user_id in session → redirects to /login."""
    s = requests.Session()
    resp = s.get(f"{live_server}/login/mfa", allow_redirects=False)
    # Route exists; without mfa_pending_user_id it redirects back to /login
    assert resp.status_code == 302, f"Expected 302 got {resp.status_code}: {resp.text[:200]}"
    assert "/login" in resp.headers.get("Location", ""), (
        f"Expected redirect to /login, got: {resp.headers.get('Location')}"
    )
    s.close()


def test_reauth_unauthenticated_redirects_to_login(live_server, seeded, http_app):
    """GET /reauth unauthenticated → redirects to /login."""
    s = requests.Session()
    resp = s.get(f"{live_server}/reauth", allow_redirects=False)
    assert resp.status_code == 302, f"Expected 302 got {resp.status_code}: {resp.text[:200]}"
    assert "/login" in resp.headers.get("Location", ""), (
        f"Expected redirect to /login, got: {resp.headers.get('Location')}"
    )
    s.close()


def test_reauth_authenticated_returns_200(live_server, seeded, http_app):
    """GET /reauth authenticated → 200 (page rendered)."""
    s = _login(live_server, "h_admin", "Admin@Practicum1")
    resp = s.get(f"{live_server}/reauth", allow_redirects=True)
    assert resp.status_code == 200, f"Expected 200 got {resp.status_code}: {resp.text[:200]}"
    s.close()


def test_change_password_requires_login(live_server, seeded, http_app):
    """GET /change-password → requires login; authenticated returns 200."""
    # Unauthenticated
    s = requests.Session()
    resp = s.get(f"{live_server}/change-password", allow_redirects=False)
    assert resp.status_code == 302, f"Expected 302 got {resp.status_code}"
    s.close()
    # Authenticated
    s = _login(live_server, "h_admin", "Admin@Practicum1")
    resp = s.get(f"{live_server}/change-password", allow_redirects=True)
    assert resp.status_code == 200, f"Expected 200 got {resp.status_code}: {resp.text[:200]}"
    s.close()


# ---------------------------------------------------------------------------
# Settings / MFA
# ---------------------------------------------------------------------------

def test_settings_mfa_requires_login_and_returns_200(live_server, seeded, http_app):
    """GET /settings/mfa → requires login (302 unauthenticated), 200 authenticated."""
    # Unauthenticated
    s = requests.Session()
    resp = s.get(f"{live_server}/settings/mfa", allow_redirects=False)
    assert resp.status_code == 302, f"Expected 302 got {resp.status_code}"
    s.close()
    # Authenticated
    s = _login(live_server, "h_admin", "Admin@Practicum1")
    resp = s.get(f"{live_server}/settings/mfa", allow_redirects=True)
    assert resp.status_code == 200, f"Expected 200 got {resp.status_code}: {resp.text[:200]}"
    s.close()


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------

def test_grading_paper_advisor_200(live_server, seeded, http_app):
    """GET /grading/paper/<id> → advisor 200."""
    paper_id = seeded["paper_id"]
    s = _login(live_server, "h_advisor", "Advisor@Practicum1")
    resp = s.get(f"{live_server}/grading/paper/{paper_id}", allow_redirects=True)
    assert resp.status_code == 200, f"Expected 200 got {resp.status_code}: {resp.text[:200]}"
    s.close()


def test_grading_paper_student_403(live_server, seeded, http_app):
    """GET /grading/paper/<id> → student gets 403."""
    paper_id = seeded["paper_id"]
    s = _login(live_server, "h_student", "Student@Practicum1")
    resp = s.get(f"{live_server}/grading/paper/{paper_id}", allow_redirects=True)
    assert resp.status_code == 403, f"Expected 403 got {resp.status_code}: {resp.text[:200]}"
    s.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def test_root_unauthenticated_redirects_to_login(live_server, seeded, http_app):
    """GET / unauthenticated → redirects to /login."""
    s = requests.Session()
    resp = s.get(f"{live_server}/", allow_redirects=False)
    assert resp.status_code == 302, f"Expected 302 got {resp.status_code}"
    location = resp.headers.get("Location", "")
    assert "/login" in location, f"Expected redirect to /login, got: {location}"
    s.close()


def test_root_authenticated_redirects_to_login(live_server, seeded, http_app):
    """GET / always redirects to /login (app/routes/main.py:home() unconditionally redirects)."""
    s = _login(live_server, "h_admin", "Admin@Practicum1")
    resp = s.get(f"{live_server}/", allow_redirects=True)
    assert resp.status_code == 200, f"Expected 200 got {resp.status_code}"
    # GET / unconditionally redirects to /login — this is the documented behavior
    assert "/login" in resp.url, f"Expected to land on /login, got: {resp.url}"
    s.close()


# ---------------------------------------------------------------------------
# Org / Cohort members
# ---------------------------------------------------------------------------

def test_cohort_members_admin_200(live_server, seeded, http_app):
    """GET /admin/org/cohorts/<id>/members → admin 200."""
    cohort_id = seeded["cohort_id"]
    s = _login(live_server, "h_admin", "Admin@Practicum1")
    resp = s.get(f"{live_server}/admin/org/cohorts/{cohort_id}/members", allow_redirects=True)
    assert resp.status_code == 200, f"Expected 200 got {resp.status_code}: {resp.text[:200]}"
    s.close()


def test_cohort_members_student_403(live_server, seeded, http_app):
    """GET /admin/org/cohorts/<id>/members → student 403."""
    cohort_id = seeded["cohort_id"]
    s = _login(live_server, "h_student", "Student@Practicum1")
    resp = s.get(f"{live_server}/admin/org/cohorts/{cohort_id}/members", allow_redirects=True)
    assert resp.status_code == 403, f"Expected 403 got {resp.status_code}: {resp.text[:200]}"
    s.close()


# ---------------------------------------------------------------------------
# Papers
# ---------------------------------------------------------------------------

def test_admin_papers_new_admin_200(live_server, seeded, http_app):
    """GET /admin/papers/new → admin 200."""
    s = _login(live_server, "h_admin", "Admin@Practicum1")
    resp = s.get(f"{live_server}/admin/papers/new", allow_redirects=True)
    assert resp.status_code == 200, f"Expected 200 got {resp.status_code}: {resp.text[:200]}"
    s.close()


def test_admin_papers_reorder_questions_200(live_server, seeded, http_app):
    """PUT /admin/papers/<id>/questions/reorder → admin 200 (empty list is valid)."""
    paper_id = seeded["paper_id"]
    question_id = seeded["question_id"]
    s = _login(live_server, "h_admin", "Admin@Practicum1")
    # Route expects JSON with key "ordered_ids" (list of question IDs)
    resp = s.put(
        f"{live_server}/admin/papers/{paper_id}/questions/reorder",
        json={"ordered_ids": [question_id]},
        headers={"HX-Request": "true"},
        allow_redirects=True,
    )
    # Returns "" (empty 200) on success
    assert resp.status_code == 200, f"Expected 200 got {resp.status_code}: {resp.text[:200]}"
    s.close()


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

def test_admin_permissions_templates_200(live_server, seeded, http_app):
    """GET /admin/permissions/templates → admin 200."""
    s = _login(live_server, "h_admin", "Admin@Practicum1")
    resp = s.get(f"{live_server}/admin/permissions/templates", allow_redirects=True)
    assert resp.status_code == 200, f"Expected 200 got {resp.status_code}: {resp.text[:200]}"
    s.close()


def test_admin_permissions_delegations_200(live_server, seeded, http_app):
    """GET /admin/permissions/delegations → admin 200."""
    s = _login(live_server, "h_admin", "Admin@Practicum1")
    resp = s.get(f"{live_server}/admin/permissions/delegations", allow_redirects=True)
    assert resp.status_code == 200, f"Expected 200 got {resp.status_code}: {resp.text[:200]}"
    s.close()


def test_admin_permissions_grant_requires_reauth(live_server, seeded, http_app):
    """POST /admin/permissions/grant → @high_risk_action redirects to /reauth first."""
    student_id = seeded["student_id"]
    s = _login(live_server, "h_admin", "Admin@Practicum1")
    resp = s.post(
        f"{live_server}/admin/permissions/grant",
        data={"user_id": student_id, "permission": "report:export"},
        allow_redirects=False,
    )
    # Should redirect to /reauth before processing
    assert resp.status_code == 302, f"Expected 302 reauth redirect got {resp.status_code}"
    assert "/reauth" in resp.headers.get("Location", ""), (
        f"Expected /reauth in Location, got: {resp.headers.get('Location')}"
    )
    s.close()


def test_admin_permissions_grant_processes_after_reauth(live_server, seeded, http_app):
    """POST /admin/permissions/grant → processes (302/200) after reauth completes."""
    student_id = seeded["student_id"]
    s = _login(live_server, "h_admin", "Admin@Practicum1")

    # Trigger reauth gate
    s.post(
        f"{live_server}/admin/permissions/grant",
        data={"user_id": student_id, "permission": "report:export"},
        allow_redirects=False,
    )
    # Complete reauth
    s.post(
        f"{live_server}/reauth",
        data={"password": "Admin@Practicum1", "next_url": "/admin/permissions/grant"},
        allow_redirects=True,
    )
    # Retry POST — should now process (not redirect to /reauth)
    resp = s.post(
        f"{live_server}/admin/permissions/grant",
        data={"user_id": student_id, "permission": "report:export"},
        allow_redirects=False,
    )
    assert resp.status_code in (200, 302), f"Expected 200/302 after reauth got {resp.status_code}"
    if resp.status_code == 302:
        assert "/reauth" not in resp.headers.get("Location", ""), (
            "Still redirecting to /reauth after completing reauth"
        )
    s.close()


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------

def test_admin_questions_edit_admin_200(live_server, seeded, http_app):
    """GET /admin/questions/<id>/edit → admin 200."""
    question_id = seeded["question_id"]
    s = _login(live_server, "h_admin", "Admin@Practicum1")
    resp = s.get(f"{live_server}/admin/questions/{question_id}/edit", allow_redirects=True)
    assert resp.status_code == 200, f"Expected 200 got {resp.status_code}: {resp.text[:200]}"
    s.close()


# ---------------------------------------------------------------------------
# Reports export
# ---------------------------------------------------------------------------

def test_reports_export_summary_without_permission_403(live_server, seeded, http_app):
    """GET /reports/paper/<id>/export/summary → advisor without report:export → 403."""
    paper_id = seeded["paper_id"]
    s = _login(live_server, "h_advisor", "Advisor@Practicum1")
    resp = s.get(f"{live_server}/reports/paper/{paper_id}/export/summary", allow_redirects=True)
    assert resp.status_code == 403, f"Expected 403 got {resp.status_code}: {resp.text[:200]}"
    s.close()


def test_reports_export_summary_admin_200(live_server, seeded, http_app):
    """GET /reports/paper/<id>/export/summary → admin (dept_admin bypasses permission) → 200."""
    paper_id = seeded["paper_id"]
    s = _login(live_server, "h_admin", "Admin@Practicum1")
    resp = s.get(f"{live_server}/reports/paper/{paper_id}/export/summary", allow_redirects=True)
    assert resp.status_code == 200, f"Expected 200 got {resp.status_code}: {resp.text[:200]}"
    s.close()


# ---------------------------------------------------------------------------
# Quiz — max attempts exhausted
# ---------------------------------------------------------------------------

def test_quiz_start_max_attempts_exhausted_400(live_server, seeded, http_app):
    """POST /quiz/<id>/start when max_attempts exhausted → 400 + 'No attempts remaining'."""
    from datetime import datetime, timezone, timedelta
    from app.extensions import db
    from app.models.attempt import Attempt
    from app.models.paper import Paper

    paper_id = seeded["paper_id"]
    student_id = seeded["student_id"]

    # Seed a paper with max_attempts=1 and one finalized attempt
    with http_app.app_context():
        paper = db.session.get(Paper, paper_id)
        paper.max_attempts = 1
        db.session.add(paper)
        # Remove any existing attempts for this student+paper to start clean
        Attempt.query.filter_by(paper_id=paper_id, student_id=student_id).delete()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        attempt = Attempt(
            paper_id=paper_id,
            student_id=student_id,
            status="finalized",
            started_at=now - timedelta(hours=1),
            finalized_at=now - timedelta(minutes=30),
            time_limit_min=45,
            expires_at=now + timedelta(hours=1),
            autosave_count=0,
            submission_token=None,
        )
        db.session.add(attempt)
        db.session.commit()

    s = _login(live_server, "h_student", "Student@Practicum1")
    resp = s.post(f"{live_server}/quiz/{paper_id}/start", allow_redirects=False)
    assert resp.status_code == 400, f"Expected 400 got {resp.status_code}: {resp.text[:300]}"
    assert "No attempts remaining" in resp.text, (
        f"Expected 'No attempts remaining' in body, got: {resp.text[:300]}"
    )
    s.close()


# ---------------------------------------------------------------------------
# Gap 1 (fixed): DELETE /admin/permissions/delegations/<id> happy path
# ---------------------------------------------------------------------------

def test_revoke_delegation_with_reauth_sets_inactive(live_server, seeded, http_app):
    """DELETE /admin/permissions/delegations/<id> after reauth sets is_active=False."""
    from app.extensions import db
    from app.models.permission import TemporaryDelegation
    from datetime import datetime, timezone, timedelta

    # Seed a delegation to revoke
    with http_app.app_context():
        admin_id = seeded["admin_id"]
        student_id = seeded["student_id"]
        d = TemporaryDelegation(
            delegator_id=admin_id,
            delegate_id=student_id,
            scope="scope:global",
            permissions='["cohort:view"]',
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7),
            is_active=True,
        )
        db.session.add(d)
        db.session.commit()
        delegation_id = d.id

    s = _login(live_server, "h_admin", "Admin@Practicum1")
    url = f"/admin/permissions/delegations/{delegation_id}"

    # Trigger reauth gate
    s.delete(f"{live_server}{url}", allow_redirects=False)
    # Complete reauth
    s.post(f"{live_server}/reauth",
           data={"password": "Admin@Practicum1", "next_url": url},
           allow_redirects=True)
    # Retry DELETE — should now revoke
    resp = s.delete(f"{live_server}{url}", allow_redirects=False)
    assert resp.status_code in (200, 302), f"Expected 200/302 after reauth, got {resp.status_code}"
    if resp.status_code == 302:
        assert "/reauth" not in resp.headers.get("Location", ""), "Still redirecting to /reauth"

    # Verify DB: delegation is now inactive
    with http_app.app_context():
        d = db.session.get(TemporaryDelegation, delegation_id)
        assert d.is_active is False, f"Expected is_active=False, got {d.is_active}"
    s.close()


# ---------------------------------------------------------------------------
# Gap 2 (fixed): grant permission → assert UserPermission row persisted
# ---------------------------------------------------------------------------

def test_admin_permissions_grant_persists_db_row(live_server, seeded, http_app):
    """POST /admin/permissions/grant after reauth writes UserPermission row to DB."""
    from app.extensions import db
    from app.models.permission import UserPermission

    student_id = seeded["student_id"]
    permission = "cohort:export_test_unique"

    # Clean any pre-existing row with this test permission
    with http_app.app_context():
        UserPermission.query.filter_by(
            user_id=student_id, permission=permission
        ).delete()
        db.session.commit()

    s = _login(live_server, "h_admin", "Admin@Practicum1")

    # Trigger reauth gate
    s.post(f"{live_server}/admin/permissions/grant",
           data={"user_id": student_id, "permission": permission},
           allow_redirects=False)
    # Complete reauth
    s.post(f"{live_server}/reauth",
           data={"password": "Admin@Practicum1", "next_url": "/admin/permissions/grant"},
           allow_redirects=True)
    # Retry — should process
    resp = s.post(f"{live_server}/admin/permissions/grant",
                  data={"user_id": student_id, "permission": permission},
                  allow_redirects=True)
    assert resp.status_code in (200, 302), f"Expected 200/302 got {resp.status_code}"

    # Assert DB row was written
    with http_app.app_context():
        row = UserPermission.query.filter_by(
            user_id=student_id, permission=permission
        ).first()
        assert row is not None, "UserPermission row was NOT written to DB after grant"
    s.close()


# ---------------------------------------------------------------------------
# Gap 3 (fixed): remaining export variants with permission check
# ---------------------------------------------------------------------------

def _grant_export_perm(http_app, user_id):
    """Grant report:export to user directly in DB."""
    from app.extensions import db
    from app.models.permission import UserPermission
    with http_app.app_context():
        if not UserPermission.query.filter_by(user_id=user_id, permission="report:export").first():
            db.session.add(UserPermission(user_id=user_id, permission="report:export"))
            db.session.commit()


def test_reports_export_students_with_permission_200(live_server, seeded, http_app):
    """GET /reports/paper/<id>/export/students with report:export → 200 CSV attachment."""
    _grant_export_perm(http_app, seeded["advisor_id"])
    paper_id = seeded["paper_id"]
    s = _login(live_server, "h_advisor", "Advisor@Practicum1")
    resp = s.get(f"{live_server}/reports/paper/{paper_id}/export/students", allow_redirects=True)
    assert resp.status_code == 200, f"Expected 200 got {resp.status_code}: {resp.text[:200]}"
    assert "attachment" in resp.headers.get("Content-Disposition", ""), (
        f"Expected attachment, got: {resp.headers.get('Content-Disposition')}"
    )
    s.close()


def test_reports_export_difficulty_with_permission_200(live_server, seeded, http_app):
    """GET /reports/paper/<id>/export/difficulty with report:export → 200 CSV attachment."""
    _grant_export_perm(http_app, seeded["advisor_id"])
    paper_id = seeded["paper_id"]
    s = _login(live_server, "h_advisor", "Advisor@Practicum1")
    resp = s.get(f"{live_server}/reports/paper/{paper_id}/export/difficulty", allow_redirects=True)
    assert resp.status_code == 200, f"Expected 200 got {resp.status_code}: {resp.text[:200]}"
    assert "attachment" in resp.headers.get("Content-Disposition", ""), (
        f"Expected attachment, got: {resp.headers.get('Content-Disposition')}"
    )
    s.close()


def test_reports_export_cohort_comparison_with_permission_200(live_server, seeded, http_app):
    """GET /reports/paper/<id>/export/cohort-comparison with report:export → 200 CSV attachment."""
    _grant_export_perm(http_app, seeded["advisor_id"])
    paper_id = seeded["paper_id"]
    s = _login(live_server, "h_advisor", "Advisor@Practicum1")
    resp = s.get(f"{live_server}/reports/paper/{paper_id}/export/cohort-comparison", allow_redirects=True)
    assert resp.status_code == 200, f"Expected 200 got {resp.status_code}: {resp.text[:200]}"
    assert "attachment" in resp.headers.get("Content-Disposition", ""), (
        f"Expected attachment, got: {resp.headers.get('Content-Disposition')}"
    )
    s.close()


def test_reports_export_students_without_permission_403(live_server, seeded, http_app):
    """GET /reports/paper/<id>/export/students without report:export → 403."""
    from app.extensions import db
    from app.models.permission import UserPermission
    paper_id = seeded["paper_id"]
    # Ensure advisor does NOT have export permission
    with http_app.app_context():
        UserPermission.query.filter_by(
            user_id=seeded["advisor_id"], permission="report:export"
        ).delete()
        db.session.commit()
    s = _login(live_server, "h_advisor", "Advisor@Practicum1")
    resp = s.get(f"{live_server}/reports/paper/{paper_id}/export/students", allow_redirects=True)
    assert resp.status_code == 403, f"Expected 403 got {resp.status_code}"
    s.close()
