from app.extensions import db
from app.models.login_attempt import LoginAttempt
from app.models.permission import UserPermission
from app.models.user import User


def login_as(client, username):
    password_map = {
        "admin": "Admin@Practicum1",
        "student1": "Student@Practicum1",
    }
    client.post("/login", data={"username": username, "password": password_map.get(username, "Admin@Practicum1")})


def test_post_login_valid_redirects_dashboard(client, admin_user):
    res = client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"}, follow_redirects=False)
    assert res.status_code == 302
    assert "/dashboard" in res.headers.get("Location", "")


def test_post_login_invalid_returns_inline_error_fragment(client, admin_user):
    res = client.post("/login", data={"username": "admin", "password": "Wrong123!"}, headers={"HX-Request": "true"})
    assert res.status_code == 200
    assert "Invalid username or password" in res.get_data(as_text=True)


def test_post_login_after_3_fails_shows_captcha(client, app, admin_user):
    for _ in range(3):
        client.post("/login", data={"username": "admin", "password": "Wrong123!"}, headers={"HX-Request": "true"})
    res = client.post("/login", data={"username": "admin", "password": "Wrong123!"}, headers={"HX-Request": "true"})
    assert "CAPTCHA" in res.get_data(as_text=True)


def test_get_dashboard_without_session_redirects_login(client):
    res = client.get("/dashboard", follow_redirects=False)
    assert res.status_code == 302
    assert "/login" in res.headers.get("Location", "")


def test_get_logout_clears_session(client, admin_user):
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    res = client.get("/logout", follow_redirects=False)
    assert res.status_code == 302
    assert "/login" in res.headers.get("Location", "")


def test_8_failed_logins_triggers_lockout(client, admin_user):
    """8 consecutive wrong passwords must trigger account lockout."""
    for _ in range(8):
        client.post("/login", data={"username": "admin", "password": "WrongPass1!"})
    res = client.post(
        "/login",
        data={"username": "admin", "password": "WrongPass1!"},
        headers={"HX-Request": "true"},
    )
    body = res.get_data(as_text=True)
    assert "locked" in body.lower() or "too many" in body.lower()


def test_session_lifetime_fallback_reads_session_lifetime_minutes_env(monkeypatch):
    """Outside an app context, idle timeout must follow SESSION_LIFETIME_MINUTES."""
    from datetime import timedelta

    monkeypatch.setenv("SESSION_LIFETIME_MINUTES", "5")
    from app.services import session_service

    assert session_service._session_lifetime() == timedelta(minutes=5)


def test_expired_session_redirects_to_login(client, admin_user):
    """Stale last_active_at must cause redirect to /login?reason=expired."""
    from datetime import datetime, timedelta, timezone

    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    # Direct injection: no endpoint path for this state transition — last_active_at
    # must be backdated to simulate an expired session; no public endpoint can do this.
    with client.session_transaction() as sess:
        expired_ts = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=35)).isoformat()
        sess["last_active_at"] = expired_ts
    res = client.get("/dashboard", follow_redirects=False)
    assert res.status_code == 302
    loc = res.headers.get("Location", "")
    assert "/login" in loc
    assert "expired" in loc


def test_post_switch_role_changes_active_role(client, admin_user, app):
    """Authenticated user can switch to an extra granted role."""
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    with app.app_context():
        admin = User.query.filter_by(username="admin").first()
        grant = UserPermission(user_id=admin.id, permission="role:faculty_advisor")
        db.session.add(grant)
        db.session.commit()
    # Trigger the reauth redirect so the action is stored in the session, then complete it
    client.post("/switch-role", data={"role": "faculty_advisor"}, follow_redirects=False)
    client.post("/reauth", data={"password": "Admin@Practicum1", "next_url": "/switch-role"}, follow_redirects=False)
    res = client.post("/switch-role", data={"role": "faculty_advisor"}, follow_redirects=False)
    assert res.status_code in (302, 204)
    with client.session_transaction() as sess:
        assert sess.get("active_role") == "faculty_advisor"


def test_post_switch_role_to_unavailable_role_returns_403(client, admin_user):
    """User cannot switch to a role they are not granted."""
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    # Trigger the reauth redirect for switch_role_submit, then complete reauth
    client.post("/switch-role", data={"role": "student"}, follow_redirects=False)
    client.post("/reauth", data={"password": "Admin@Practicum1", "next_url": "/switch-role"}, follow_redirects=False)
    res = client.post("/switch-role", data={"role": "student"})
    assert res.status_code == 403


def test_get_switch_role_page_returns_200(client, admin_user):
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    res = client.get("/switch-role")
    assert res.status_code == 200


def test_login_succeeds_after_captcha_with_correct_answer(client, app, admin_user):
    """After 3 failed logins (CAPTCHA triggered), submitting the correct CAPTCHA
    and correct password must succeed and redirect to /dashboard."""
    from app.services.auth_service import generate_captcha

    for _ in range(3):
        client.post("/login", data={"username": "admin", "password": "Wrong123!"})

    question, answer = generate_captcha()
    assert question
    # Direct injection: no endpoint path for this state transition — captcha_expected
    # is server-side session state that cannot be retrieved via any public endpoint.
    with client.session_transaction() as sess:
        sess["captcha_expected"] = answer

    res = client.post(
        "/login",
        data={
            "username": "admin",
            "password": "Admin@Practicum1",
            "captcha_answer": answer,
        },
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert "/dashboard" in res.headers.get("Location", "")


def test_post_switch_role_without_reauth_redirects_to_reauth(client, admin_user, app):
    """POST /switch-role without prior re-authentication must redirect to /reauth."""
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    with app.app_context():
        admin = User.query.filter_by(username="admin").first()
        grant = UserPermission(user_id=admin.id, permission="role:faculty_advisor")
        db.session.add(grant)
        db.session.commit()
    res = client.post("/switch-role", data={"role": "faculty_advisor"}, follow_redirects=False)
    assert res.status_code == 302
    assert "/reauth" in res.headers.get("Location", "")


def test_post_switch_role_after_reauth_succeeds(client, admin_user, app):
    """POST /switch-role after valid re-authentication must succeed."""
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    with app.app_context():
        admin = User.query.filter_by(username="admin").first()
        grant = UserPermission(user_id=admin.id, permission="role:faculty_advisor")
        db.session.add(grant)
        db.session.commit()
    # Trigger the reauth redirect so the action is stored in the session, then complete it
    client.post("/switch-role", data={"role": "faculty_advisor"}, follow_redirects=False)
    client.post("/reauth", data={"password": "Admin@Practicum1", "next_url": "/switch-role"}, follow_redirects=False)
    res = client.post("/switch-role", data={"role": "faculty_advisor"}, follow_redirects=False)
    assert res.status_code in (302, 204)
    with client.session_transaction() as sess:
        assert sess.get("active_role") == "faculty_advisor"


def test_dashboard_shows_admin_section_for_dept_admin(client, dept_admin):
    """dept_admin active_role shows admin summary section."""
    login_as(client, "admin")
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    data = resp.get_data(as_text=True)
    assert "Schools" in data


def test_dashboard_shows_student_section_for_student(client, student):
    """student active_role shows student assessments section, NOT admin section."""
    login_as(client, "student1")
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    data = resp.get_data(as_text=True)
    assert "My Assessments" in data
    assert "Administration Summary" not in data


def test_switched_role_limits_report_scope_to_assigned_cohorts(client, app, seeded_assessment):
    """A dept_admin who switches to faculty_advisor must only see assigned-cohort papers
    in /reports, not all cohort papers."""
    with app.app_context():
        admin = User.query.filter_by(username="admin").first()
        perm = UserPermission(user_id=admin.id, permission="role:faculty_advisor")
        db.session.add(perm)
        db.session.commit()

    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    # Trigger the reauth redirect for switch_role_submit, then complete it via /reauth
    client.post("/switch-role", data={"role": "faculty_advisor"}, follow_redirects=False)
    client.post("/reauth", data={"password": "Admin@Practicum1", "next_url": "/switch-role"}, follow_redirects=False)

    res = client.post("/switch-role", data={"role": "faculty_advisor"}, follow_redirects=True)
    assert res.status_code == 200

    res = client.get("/reports")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    from app.models.paper import Paper

    with app.app_context():
        paper2 = Paper.query.get(seeded_assessment["paper2_id"])
        if paper2:
            assert paper2.title not in html, (
                "Switched-role advisor saw a paper from an unassigned cohort"
            )


def test_cross_user_session_isolation(client, seeded_assessment):
    """No stale state from user A must be visible after logging in as user B."""
    # Log in as admin and confirm dashboard access
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    res = client.get("/dashboard")
    assert res.status_code == 200

    # Log out (logout route is GET)
    client.get("/logout")

    # Log in as student1
    client.post("/login", data={"username": "student1", "password": "Student@Practicum1"})

    # Student can reach their own dashboard
    res = client.get("/dashboard")
    assert res.status_code == 200

    # Student cannot reach admin-only routes
    res = client.get("/admin/users", follow_redirects=False)
    assert res.status_code in (302, 403)

    res = client.get("/admin/audit-logs", follow_redirects=False)
    assert res.status_code in (302, 403)

    # Log out
    client.get("/logout")

    # After logout, dashboard redirects back to login (session is cleared)
    res = client.get("/dashboard", follow_redirects=False)
    assert res.status_code == 302
    assert "/login" in res.headers.get("Location", "")


def test_force_password_change_redirects_to_change_page(client, app):
    """User with force_password_change=True must be redirected to /change-password."""
    with app.app_context():
        from app.services.auth_service import hash_password

        u = User(
            username="force_change_user",
            password_hash=hash_password("ForceChange@1234"),
            role="student",
            is_active=True,
            force_password_change=True,
        )
        db.session.add(u)
        db.session.commit()

    client.post("/login", data={"username": "force_change_user", "password": "ForceChange@1234"})
    res = client.get("/dashboard", follow_redirects=False)
    assert res.status_code == 302
    assert "/change-password" in res.headers.get("Location", "")


def test_force_password_change_clears_flag_after_success(client, app):
    """Successful /change-password POST clears the force_password_change flag."""
    with app.app_context():
        from app.services.auth_service import hash_password

        u = User(
            username="force_change_user2",
            password_hash=hash_password("ForceChange@1234"),
            role="student",
            is_active=True,
            force_password_change=True,
        )
        db.session.add(u)
        db.session.commit()

    client.post("/login", data={"username": "force_change_user2", "password": "ForceChange@1234"})
    res = client.post(
        "/change-password",
        data={"new_password": "NewSecure@9999!", "confirm_password": "NewSecure@9999!"},
        follow_redirects=False,
    )
    assert res.status_code in (302, 204)

    with app.app_context():
        u = User.query.filter_by(username="force_change_user2").first()
        assert not u.force_password_change


def test_force_password_change_password_mismatch_returns_error(client, app):
    """Mismatched passwords on /change-password returns 200 with error."""
    with app.app_context():
        from app.services.auth_service import hash_password

        u = User(
            username="force_change_user3",
            password_hash=hash_password("ForceChange@1234"),
            role="student",
            is_active=True,
            force_password_change=True,
        )
        db.session.add(u)
        db.session.commit()

    client.post("/login", data={"username": "force_change_user3", "password": "ForceChange@1234"})
    res = client.post(
        "/change-password",
        data={"new_password": "NewSecure@9999!", "confirm_password": "DifferentPass@9999!"},
    )
    assert res.status_code == 200
    assert "do not match" in res.get_data(as_text=True).lower()


def test_switched_role_permission_required_uses_active_role(client, app):
    """After switching to student role, permission_required('cohort:view') must deny access.

    Regression: previously has_permission used user.role (faculty_advisor) instead of
    the active session role (student), so the guard was bypassed.
    """
    from app.extensions import db
    from app.models.assignment import CohortMember
    from app.models.org import Class, Cohort, Major, School
    from app.models.permission import UserPermission
    from app.services.auth_service import hash_password

    with app.app_context():
        advisor = User(
            username="switched_advisor_test",
            password_hash=hash_password("Advisor@Switch1"),
            role="faculty_advisor",
            is_active=True,
        )
        db.session.add(advisor)
        db.session.flush()
        # grant role:student so they can switch
        db.session.add(UserPermission(user_id=advisor.id, permission="role:student"))
        school = School(name="SwitchSchool", code="SW")
        db.session.add(school)
        db.session.flush()
        major = Major(name="SwMaj", code="SM", school_id=school.id)
        db.session.add(major)
        db.session.flush()
        clazz = Class(name="SwClass", year=2026, major_id=major.id)
        db.session.add(clazz)
        db.session.flush()
        cohort = Cohort(name="SwCohort", class_id=clazz.id, is_active=True)
        db.session.add(cohort)
        db.session.flush()
        db.session.add(CohortMember(cohort_id=cohort.id, user_id=advisor.id, role_in_cohort="faculty_advisor"))
        db.session.commit()
        cohort_id = cohort.id

    client.post("/login", data={"username": "switched_advisor_test", "password": "Advisor@Switch1"})

    # Switch to student role (requires reauth)
    first = client.post("/switch-role", data={"role": "student"}, follow_redirects=False)
    assert "/reauth" in first.headers.get("Location", "")
    client.post(
        "/reauth",
        data={"password": "Advisor@Switch1", "next_url": "/switch-role"},
        follow_redirects=False,
    )
    switched = client.post("/switch-role", data={"role": "student"}, follow_redirects=False)
    assert switched.status_code in (302, 204)

    # As student role, cohort detail must be denied (student lacks cohort:view)
    res = client.get(f"/cohorts/{cohort_id}", follow_redirects=False)
    assert res.status_code == 403
