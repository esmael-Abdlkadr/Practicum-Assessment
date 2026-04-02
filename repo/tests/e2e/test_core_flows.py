"""
E2E tests for critical HTMX-powered browser interactions.
Requires a running Flask app (handled by the live_app fixture).
"""

import re

import pytest
from playwright.sync_api import Page, expect


@pytest.fixture(autouse=True)
def reset_context(page: Page, base_url: str):
    page.goto(f"{base_url}/login")
    yield
    page.context.clear_cookies()


def login(page: Page, base_url: str, username: str, password: str):
    page.goto(f"{base_url}/login")
    page.fill("input[name='username']", username)
    page.fill("input[name='password']", password)
    page.click("button[type='submit']")
    page.wait_for_url(f"{base_url}/dashboard", timeout=5000)


def test_login_page_loads(page: Page, base_url: str):
    page.goto(f"{base_url}/login")
    expect(page).to_have_title(re.compile(r"Practicum", re.IGNORECASE))
    expect(page.locator("input[name='username']")).to_be_visible()
    expect(page.locator("input[name='password']")).to_be_visible()


def test_login_invalid_shows_inline_error(page: Page, base_url: str):
    """HTMX fragment swap must show inline error without full-page reload."""
    page.goto(f"{base_url}/login")
    url_before = page.url
    page.fill("input[name='username']", "nonexistent")
    page.fill("input[name='password']", "wrongpassword")
    page.click("button[type='submit']")
    page.wait_for_selector(".alert-danger", timeout=3000)
    assert page.url == url_before
    assert "Invalid" in page.locator(".alert-danger").inner_text()


def test_login_success_redirects_to_dashboard(page: Page, base_url: str, live_app):
    """Successful login must redirect to /dashboard."""
    with live_app.app_context():
        from app.extensions import db
        from app.models.user import User
        from app.services.auth_service import hash_password

        if not User.query.filter_by(username="e2e_admin").first():
            u = User(
                username="e2e_admin",
                password_hash=hash_password("E2eAdmin@2024!"),
                role="dept_admin",
                full_name="E2E Admin",
                is_active=True,
            )
            db.session.add(u)
            db.session.commit()

    login(page, base_url, "e2e_admin", "E2eAdmin@2024!")
    expect(page).to_have_url(f"{base_url}/dashboard")


def test_unauthenticated_dashboard_redirects_to_login(page: Page, base_url: str):
    """Unauthenticated access to /dashboard must redirect to /login."""
    page.goto(f"{base_url}/dashboard")
    expect(page).to_have_url(re.compile(r"/login"))


def test_health_endpoint(page: Page, base_url: str):
    """Health check must return 200."""
    resp = page.goto(f"{base_url}/health")
    assert resp.status == 200


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_user(live_app, username: str, password: str, role: str):
    with live_app.app_context():
        from app.extensions import db
        from app.models.user import User
        from app.services.auth_service import hash_password

        if not User.query.filter_by(username=username).first():
            u = User(
                username=username,
                password_hash=hash_password(password),
                role=role,
                full_name=username.replace("_", " ").title(),
                is_active=True,
            )
            db.session.add(u)
            db.session.commit()


# ---------------------------------------------------------------------------
# Role-switch flow
# ---------------------------------------------------------------------------

def test_role_switch_redirects_to_dashboard(page: Page, base_url: str, live_app):
    """Dept admin can reach switch-role page and it renders available roles."""
    _create_user(live_app, "e2e_admin_rs", "E2eAdmin@2024!", "dept_admin")
    login(page, base_url, "e2e_admin_rs", "E2eAdmin@2024!")

    page.goto(f"{base_url}/switch-role")
    expect(page).to_have_url(re.compile(r"/switch-role"))
    expect(page.locator("form")).to_be_visible()
    # Page must show at least one role option
    expect(page.locator("input[name='role']").first).to_be_visible()


# ---------------------------------------------------------------------------
# Admin organisation management
# ---------------------------------------------------------------------------

def test_admin_can_view_schools_list(page: Page, base_url: str, live_app):
    """Dept admin can load the school management page."""
    _create_user(live_app, "e2e_admin_org", "E2eAdmin@2024!", "dept_admin")
    login(page, base_url, "e2e_admin_org", "E2eAdmin@2024!")

    resp = page.goto(f"{base_url}/admin/org/schools")
    assert resp.status == 200
    expect(page.locator("body")).to_contain_text(re.compile(r"school|organisation|org", re.IGNORECASE))


# ---------------------------------------------------------------------------
# Student quiz list
# ---------------------------------------------------------------------------

def test_student_sees_quiz_list_page(page: Page, base_url: str, live_app):
    """Student can reach the quiz/papers list after login."""
    _create_user(live_app, "e2e_student_q", "Student@Practicum1!", "student")
    login(page, base_url, "e2e_student_q", "Student@Practicum1!")

    resp = page.goto(f"{base_url}/quiz")
    # Student with no cohort membership should see the page (even if empty), not a 500.
    assert resp.status in (200, 302)


# ---------------------------------------------------------------------------
# Force-password-change flow
# ---------------------------------------------------------------------------

def test_force_password_change_redirects_and_allows_reset(page: Page, base_url: str, live_app):
    """User with force_password_change flag is redirected and can set a new password."""
    with live_app.app_context():
        from app.extensions import db
        from app.models.user import User
        from app.services.auth_service import hash_password

        u = User.query.filter_by(username="e2e_force_chg").first()
        if not u:
            u = User(
                username="e2e_force_chg",
                password_hash=hash_password("OldPass@1234!"),
                role="student",
                is_active=True,
                force_password_change=True,
            )
            db.session.add(u)
        else:
            u.force_password_change = True
        db.session.commit()

    page.goto(f"{base_url}/login")
    page.fill("input[name='username']", "e2e_force_chg")
    page.fill("input[name='password']", "OldPass@1234!")
    page.click("button[type='submit']")
    page.wait_for_timeout(1000)

    # After login, any protected page should redirect to /change-password
    page.goto(f"{base_url}/dashboard")
    expect(page).to_have_url(re.compile(r"/change-password"))

    # Fill out the change-password form
    page.fill("input[name='new_password']", "NewPass@Secure99!")
    page.fill("input[name='confirm_password']", "NewPass@Secure99!")
    page.click("button[type='submit']")
    page.wait_for_timeout(1500)

    # Should now land on dashboard (flag cleared)
    expect(page).to_have_url(re.compile(r"/dashboard"))


# ---------------------------------------------------------------------------
# Reports page access
# ---------------------------------------------------------------------------

def test_admin_can_view_reports_page(page: Page, base_url: str, live_app):
    """Dept admin can access the reports landing page."""
    _create_user(live_app, "e2e_admin_rep", "E2eAdmin@2024!", "dept_admin")
    login(page, base_url, "e2e_admin_rep", "E2eAdmin@2024!")

    resp = page.goto(f"{base_url}/reports")
    assert resp.status == 200


# ---------------------------------------------------------------------------
# Custom error pages
# ---------------------------------------------------------------------------

def test_404_renders_custom_page(page: Page, base_url: str):
    """Non-existent routes should show the custom 404 page, not a raw Flask error."""
    resp = page.goto(f"{base_url}/this-route-does-not-exist-at-all-xyz")
    assert resp.status == 404
    expect(page.locator("body")).to_contain_text(re.compile(r"404|not found", re.IGNORECASE))


def test_logout_clears_session_e2e(page: Page, base_url: str, live_app):
    """Logout must clear session so /dashboard redirects back to login."""
    _create_user(live_app, "e2e_logout_usr", "E2eAdmin@2024!", "dept_admin")
    login(page, base_url, "e2e_logout_usr", "E2eAdmin@2024!")

    page.goto(f"{base_url}/logout")
    page.wait_for_timeout(500)

    page.goto(f"{base_url}/dashboard")
    expect(page).to_have_url(re.compile(r"/login"))


# ---------------------------------------------------------------------------
# Student direct-URL access denial
# ---------------------------------------------------------------------------

def test_student_cannot_access_admin_urls_directly(page: Page, base_url: str, live_app):
    """Student who navigates directly to admin/report/grading URLs must be denied."""
    _create_user(live_app, "e2e_student_deny", "Student@Deny2024!", "student")
    login(page, base_url, "e2e_student_deny", "Student@Deny2024!")

    for path in ["/admin/dashboard", "/admin/users", "/admin/audit-logs"]:
        resp = page.goto(f"{base_url}{path}")
        assert resp.status in (302, 403), f"Expected denial for {path}, got {resp.status}"


# ---------------------------------------------------------------------------
# Cohort-filtered reports navigation
# ---------------------------------------------------------------------------

def test_cohort_view_reports_link_filters_papers(page: Page, base_url: str, live_app):
    """'View Reports' from cohort list must narrow the reports page to that cohort."""
    import json
    from datetime import datetime, timezone

    with live_app.app_context():
        from app.extensions import db
        from app.models.assignment import CohortMember
        from app.models.org import Class, Cohort, Major, School
        from app.models.paper import Paper, PaperQuestion
        from app.models.question import Question
        from app.models.user import User
        from app.services.auth_service import hash_password

        # create advisor and seed minimal org + paper
        if not User.query.filter_by(username="e2e_advisor_cohort").first():
            advisor = User(
                username="e2e_advisor_cohort",
                password_hash=hash_password("Advisor@Cohort1!"),
                role="faculty_advisor",
                is_active=True,
            )
            db.session.add(advisor)
            db.session.flush()

            school = School(name="E2E School", code="E2ESCH")
            db.session.add(school)
            db.session.flush()
            major = Major(name="E2E Major", code="E2EMAJ", school_id=school.id)
            db.session.add(major)
            db.session.flush()
            clazz = Class(name="E2E Class", year=2026, major_id=major.id)
            db.session.add(clazz)
            db.session.flush()
            cohort = Cohort(name="E2E Cohort Filter", class_id=clazz.id, is_active=True)
            db.session.add(cohort)
            db.session.flush()
            db.session.add(CohortMember(cohort_id=cohort.id, user_id=advisor.id, role_in_cohort="faculty_advisor"))

            paper = Paper(
                title="E2E Filter Paper",
                cohort_id=cohort.id,
                status="published",
                time_limit_min=45,
                max_attempts=1,
            )
            db.session.add(paper)
            db.session.commit()

    login(page, base_url, "e2e_advisor_cohort", "Advisor@Cohort1!")

    # go to cohort list
    resp = page.goto(f"{base_url}/cohorts")
    assert resp.status == 200

    # click the "View Reports" link for the cohort
    view_reports_link = page.locator("a", has_text="View Reports").first
    expect(view_reports_link).to_be_visible()
    view_reports_link.click()
    page.wait_for_load_state("networkidle")

    # should be on /reports with cohort_id query param
    expect(page).to_have_url(re.compile(r"/reports\?cohort_id=\d+"))
    # filter banner should be visible
    expect(page.locator("body")).to_contain_text(re.compile(r"selected cohort|Clear filter", re.IGNORECASE))
