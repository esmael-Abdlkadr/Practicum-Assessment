from datetime import datetime, timedelta, timezone
import re

from app.extensions import db
from app.models.permission import TemporaryDelegation
from app.models.user import User


def login_as(client, username):
    password_map = {
        "admin": "Admin@Practicum1",
        "regular_user": "Student@Practicum1",
        "student1": "Student@Practicum1",
        "advisor1": "Advisor@Practicum1",
    }
    client.post("/login", data={"username": username, "password": password_map.get(username, "Admin@Practicum1")})


def test_post_admin_users_weak_password_422(client, admin_user):
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    res = client.post("/admin/users", data={"username": "weakuser", "role": "student", "password": "weak"}, headers={"HX-Request": "true"})
    assert res.status_code == 422


def test_put_admin_user_role_change_without_reauth_redirects(client, app, admin_user):
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    with app.app_context():
        u = User(username="editme", role="student", password_hash="x", is_active=True)
        db.session.add(u)
        db.session.commit()
        uid = u.id
    res = client.put(f"/admin/users/{uid}", data={"role": "faculty_advisor"}, follow_redirects=False)
    assert res.status_code == 302
    assert "/reauth" in res.headers.get("Location", "")


def test_post_permission_template_without_reauth_redirects(client, admin_user):
    """Creating a permission template requires re-authentication."""
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    res = client.post(
        "/admin/permissions/templates",
        data={"name": "Test Template", "permissions": "cohort:view"},
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert "/reauth" in res.headers.get("Location", "")


def test_post_permission_grant_without_reauth_redirects(client, app, admin_user):
    """Granting user permissions requires re-authentication."""
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    with app.app_context():
        target = User(username="perm_target", role="student", password_hash="x", is_active=True)
        db.session.add(target)
        db.session.commit()
        target_id = target.id
    res = client.post(
        f"/admin/permissions/users/{target_id}/grant",
        data={"permission": "cohort:view"},
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert "/reauth" in res.headers.get("Location", "")


def test_post_delegation_without_reauth_redirects(client, admin_user):
    """Creating a delegation requires re-authentication."""
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    res = client.post(
        "/admin/permissions/delegations",
        data={"delegator_id": "1", "delegate_id": "1", "scope": "test", "permissions": "cohort:view"},
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert "/reauth" in res.headers.get("Location", "")


def test_delete_delegation_without_reauth_redirects(client, app, admin_user):
    """Revoking a delegation requires re-authentication."""
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    with app.app_context():
        admin = User.query.filter_by(username="admin").first()
        delegation = TemporaryDelegation(
            delegator_id=admin.id,
            delegate_id=admin.id,
            scope="test",
            permissions='["cohort:view"]',
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1),
            is_active=True,
        )
        db.session.add(delegation)
        db.session.commit()
        delegation_id = delegation.id
    res = client.delete(f"/admin/permissions/delegations/{delegation_id}", follow_redirects=False)
    assert res.status_code == 302
    assert "/reauth" in res.headers.get("Location", "")


def test_post_admin_user_unlock_clears_locked_until(client, app, admin_user):
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    with app.app_context():
        u = User(username="locked1", role="student", password_hash="x", is_active=True)
        u.locked_until = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=5)
        u.failed_attempts = 8
        db.session.add(u)
        db.session.commit()
        uid = u.id
    client.post(f"/admin/users/{uid}/unlock", headers={"HX-Request": "true"})
    with app.app_context():
        u = db.session.get(User, uid)
        assert u.locked_until is None
        assert u.failed_attempts == 0


def test_get_audit_logs_non_admin_forbidden(client, app, student_user):
    client.post("/login", data={"username": "student1", "password": "Student@Practicum1"})
    res = client.get("/admin/audit-logs")
    assert res.status_code == 403


def test_get_audit_logs_export_csv_download(client, admin_user):
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    res = client.get("/admin/audit-logs/export")
    assert res.status_code == 200
    assert "text/csv" in res.content_type


def test_create_user_response_does_not_expose_plaintext_password(client, auth_client):
    """Admin create-user response must not return raw plaintext password."""
    res = auth_client.post(
        "/admin/users",
        data={"username": "newuser99", "role": "student"},
        headers={"HX-Request": "true"},
    )
    body = res.get_data(as_text=True)
    assert not re.search(r"Temporary password:\s*\w{8,}", body), "Plaintext temporary password must not appear in raw response text"


def test_reset_password_response_does_not_expose_plaintext_password(client, app, auth_client):
    """Admin reset-password response must not contain plaintext credential."""
    from tests.conftest import create_user

    with app.app_context():
        u = create_user("target99", "student", "Student@Practicum1")
        uid = u.id
    with client.session_transaction() as sess:
        sess["reauth_confirmed"] = {
            "reset_password": datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        }
    res = auth_client.post(f"/admin/users/{uid}/reset-password", headers={"HX-Request": "true"})
    body = res.get_data(as_text=True)
    assert "Reveal one-time password" in body
    assert "user-select-all" not in body


def test_create_delegation_over_30_days_returns_400(client, app, admin_user):
    """Creating a delegation with expires_in_days > 30 must return 400."""
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})

    with client.session_transaction() as sess:
        from datetime import timezone

        sess["reauth_confirmed"] = {
            "create_delegation": datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        }

    with app.app_context():
        target = User(username="delegate_target2", role="faculty_advisor", password_hash="x", is_active=True)
        db.session.add(target)
        db.session.commit()
        target_id = target.id

    with app.app_context():
        admin_id = User.query.filter_by(username="admin").first().id
    res = client.post(
        "/admin/permissions/delegations",
        data={
            "delegator_id": str(admin_id),
            "delegate_id": str(target_id),
            "scope": "cohort:1",
            "permissions": "cohort:view",
            "expires_in_days": "31",
        },
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 400
    assert "30" in res.get_data(as_text=True)


def test_create_delegation_default_7_days(client, app, admin_user):
    """Creating a delegation without expires_in_days defaults to 7 days."""
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})

    with client.session_transaction() as sess:
        from datetime import timezone

        sess["reauth_confirmed"] = {
            "create_delegation": datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        }

    with app.app_context():
        target = User(username="delegate_target3", role="faculty_advisor", password_hash="x", is_active=True)
        db.session.add(target)
        db.session.commit()
        target_id = target.id

    with app.app_context():
        admin_id = User.query.filter_by(username="admin").first().id
    before = datetime.now(timezone.utc).replace(tzinfo=None)
    res = client.post(
        "/admin/permissions/delegations",
        data={
            "delegator_id": str(admin_id),
            "delegate_id": str(target_id),
            "scope": "cohort:1",
            "permissions": "cohort:view",
        },
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 200
    with app.app_context():
        d = (
            TemporaryDelegation.query.filter_by(delegator_id=admin_id, delegate_id=target_id)
            .order_by(TemporaryDelegation.id.desc())
            .first()
        )
        assert d is not None
        expected_expiry = before + timedelta(days=7)
        assert abs((d.expires_at - expected_expiry).total_seconds()) < 10


def test_create_delegation_custom_duration_is_applied(client, app, admin_user):
    """POST /admin/permissions/delegations with expires_in_days=14 must store a delegation
    expiring ~14 days from now (within ±5 minutes tolerance)."""
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    with client.session_transaction() as sess:
        sess.setdefault("reauth_confirmed", {})
        sess["reauth_confirmed"]["create_delegation"] = (
            datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        )
    with app.app_context():
        target = User.query.filter_by(username="admin").first()
    res = client.post(
        "/admin/permissions/delegations",
        data={
            "delegator_id": str(target.id),
            "delegate_id": str(target.id),
            "scope": "cohort:1",
            "permissions": "grade:view",
            "expires_in_days": "14",
        },
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 200
    with app.app_context():
        from app.models.permission import TemporaryDelegation

        d = TemporaryDelegation.query.order_by(TemporaryDelegation.id.desc()).first()
        assert d is not None
        expected = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=14)
        diff = abs((d.expires_at - expected).total_seconds())
        assert diff < 300, f"Expected ~14 days expiry, got {d.expires_at}"


def test_audit_log_search_filters_by_action(client, app, admin_user):
    """GET /admin/audit-logs/search?action=LOGIN returns only LOGIN events."""
    from app.models.audit_log import AuditLog

    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})

    with app.app_context():
        admin_id = User.query.filter_by(username="admin").first().id
        db.session.add(
            AuditLog(
                actor_id=admin_id,
                actor_username="admin",
                action="LOGIN",
                resource_type="session",
                ip_address="127.0.0.1",
                device_fingerprint="fp1",
            )
        )
        db.session.add(
            AuditLog(
                actor_id=admin_id,
                actor_username="admin",
                action="USER_CREATED",
                resource_type="user",
                ip_address="127.0.0.1",
                device_fingerprint="fp1",
            )
        )
        db.session.commit()

    res = client.get("/admin/audit-logs/search?action=LOGIN")
    assert res.status_code == 200
    body = res.get_data(as_text=True)
    assert "LOGIN" in body
    assert "USER_CREATED" not in body


def test_audit_log_search_filters_by_actor(client, app, admin_user):
    """GET /admin/audit-logs/search?actor=admin returns only events by that actor."""
    from app.models.audit_log import AuditLog
    from tests.conftest import create_user

    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})

    with app.app_context():
        admin_id = User.query.filter_by(username="admin").first().id
        other = create_user("other_actor", "faculty_advisor", "Advisor@Practicum1")
        db.session.add(
            AuditLog(
                actor_id=admin_id,
                actor_username="admin",
                action="LOGIN",
                resource_type="session",
                ip_address="127.0.0.1",
                device_fingerprint="fp1",
            )
        )
        db.session.add(
            AuditLog(
                actor_id=other.id,
                actor_username="other_actor",
                action="LOGIN",
                resource_type="session",
                ip_address="127.0.0.1",
                device_fingerprint="fp2",
            )
        )
        db.session.commit()

    res = client.get("/admin/audit-logs/search?actor=admin")
    assert res.status_code == 200
    body = res.get_data(as_text=True)
    assert "admin" in body
    assert "other_actor" not in body


def test_student_id_not_exposed_in_admin_user_list(client, app, admin_user):
    """The admin user list must not render plaintext student IDs."""
    from app.services import encryption_service
    from tests.conftest import create_user

    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})

    with app.app_context():
        s = create_user("masking_student", "student", "Student@Practicum1")
        s.student_id_enc = encryption_service.encrypt("PLAINTEXTID777")
        db.session.add(s)
        db.session.commit()

    res = client.get("/admin/users")
    assert res.status_code == 200
    body = res.get_data(as_text=True)
    assert "PLAINTEXTID777" not in body, (
        "Plaintext student ID must not appear in the admin users page"
    )


def test_create_user_does_not_expose_password_in_primary_response(client, dept_admin, db_session):
    """The primary create-user response must NOT contain the plaintext password."""
    login_as(client, "admin")
    resp = client.post(
        "/admin/users",
        data={
            "username": "tmpusertest",
            "full_name": "Tmp User",
            "email": "tmp@test.com",
            "role": "student",
        },
    )
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "<code" not in body or "one-time" in body.lower() or "reveal" in body.lower()
    assert "user-select-all" not in body


def test_reset_password_does_not_expose_password_in_primary_response(client, app, dept_admin, regular_user):
    """The primary reset-password response must NOT contain the plaintext password."""
    login_as(client, "admin")
    with app.app_context():
        uid = User.query.filter_by(username="regular_user").first().id
    with client.session_transaction() as sess:
        sess["reauth_confirmed"] = {
            "reset_password": datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        }
    resp = client.post(f"/admin/users/{uid}/reset-password")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "user-select-all" not in body


def test_get_rubric_editor_returns_200(client, dept_admin, seeded_assessment):
    """GET /admin/questions/<id>/rubric must return 200 for dept_admin."""
    login_as(client, "admin")
    qid = seeded_assessment["question_ids"][0]
    resp = client.get(f"/admin/questions/{qid}/rubric")
    assert resp.status_code == 200


def test_save_rubric_persists_criteria(client, app, dept_admin, seeded_assessment):
    """POST /admin/questions/<id>/rubric must save rubric criteria to DB."""
    login_as(client, "admin")
    qid = seeded_assessment["question_ids"][4]
    criteria = '[{"label": "Clarity", "points": 5}, {"label": "Accuracy", "points": 5}]'
    resp = client.post(
        f"/admin/questions/{qid}/rubric",
        data={"criteria": criteria},
    )
    assert resp.status_code == 200
    with app.app_context():
        from app.models.grading import Rubric

        row = Rubric.query.filter_by(question_id=qid).first()
        assert row is not None
        import json

        saved = json.loads(row.criteria)
        assert any(c.get("label") == "Clarity" for c in saved)


def test_rubric_editor_requires_dept_admin(client, student, seeded_assessment):
    """Non-admin users must get 302/403 on rubric endpoints."""
    login_as(client, "student1")
    qid = seeded_assessment["question_ids"][0]
    resp = client.get(f"/admin/questions/{qid}/rubric", follow_redirects=False)
    assert resp.status_code in (302, 403)


def test_audit_log_search_page_1_returns_results(client, dept_admin):
    """GET /admin/audit-logs/search?page=1 must return 200."""
    login_as(client, "admin")
    resp = client.get("/admin/audit-logs/search?page=1")
    assert resp.status_code == 200


def test_audit_log_search_high_page_returns_empty_not_error(client, dept_admin):
    """GET /admin/audit-logs/search?page=9999 must return 200 (empty results, no crash)."""
    login_as(client, "admin")
    resp = client.get("/admin/audit-logs/search?page=9999")
    assert resp.status_code == 200


def test_audit_log_search_page_zero_does_not_crash(client, dept_admin):
    """GET /admin/audit-logs/search?page=0 must return 200 (boundary, no crash)."""
    login_as(client, "admin")
    resp = client.get("/admin/audit-logs/search?page=0")
    assert resp.status_code == 200


def test_audit_log_search_combined_filters(client, dept_admin):
    """Combining actor + action + date range filters must return 200."""
    login_as(client, "admin")
    resp = client.get(
        "/admin/audit-logs/search"
        "?actor=admin&action=LOGIN&start_date=2020-01-01&end_date=2099-12-31&page=1"
    )
    assert resp.status_code == 200


def test_reset_password_requires_reauth(client, app, admin_user):
    """POST /admin/users/<id>/reset-password must redirect to /reauth when reauth window is absent."""
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    with app.app_context():
        admin_id = User.query.filter_by(username="admin").first().id
    res = client.post(f"/admin/users/{admin_id}/reset-password", follow_redirects=False)
    assert res.status_code == 302
    assert "/reauth" in res.headers["Location"]


def test_reveal_temp_credential_requires_reauth(client, app, admin_user):
    """GET /admin/users/<id>/reveal-temp-credential must redirect to /reauth when reauth window is absent."""
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    with app.app_context():
        admin_id = User.query.filter_by(username="admin").first().id
    res = client.get(f"/admin/users/{admin_id}/reveal-temp-credential", follow_redirects=False)
    assert res.status_code == 302
    assert "/reauth" in res.headers["Location"]


def test_reveal_temp_credential_writes_audit_log(client, app, admin_user):
    from app.models.audit_log import AuditLog

    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    client.post(
        "/admin/users",
        data={
            "username": "temp_cred_audit_user",
            "full_name": "Temp Cred",
            "email": "temp_cred_audit_user@test.local",
            "role": "student",
        },
    )

    with app.app_context():
        user_id = User.query.filter_by(username="temp_cred_audit_user").first().id

    with client.session_transaction() as sess:
        sess.setdefault("reauth_confirmed", {})
        sess["reauth_confirmed"]["reset_password"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    reset_res = client.post(f"/admin/users/{user_id}/reset-password", follow_redirects=False)
    assert reset_res.status_code == 200

    with client.session_transaction() as sess:
        sess.setdefault("reauth_confirmed", {})
        sess["reauth_confirmed"]["reveal_temp_credential"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    reveal_res = client.get(f"/admin/users/{user_id}/reveal-temp-credential", follow_redirects=False)
    assert reveal_res.status_code == 200

    with app.app_context():
        rows = AuditLog.query.filter_by(
            action="TEMP_CREDENTIAL_REVEALED",
            resource_id=str(user_id),
        ).all()
        assert len(rows) >= 1


def test_audit_log_row_has_ip_and_device_fingerprint(client, app, admin_user):
    from app.models.audit_log import AuditLog

    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    client.post(
        "/admin/users",
        data={
            "username": "audit_meta_user",
            "full_name": "Audit Meta",
            "email": "audit_meta_user@test.local",
            "role": "student",
        },
        headers={"HX-Request": "true"},
    )

    with app.app_context():
        row = AuditLog.query.filter_by(action="USER_CREATED").order_by(AuditLog.id.desc()).first()
        assert row is not None
        assert row.ip_address is not None and row.ip_address != ""
        assert row.device_fingerprint is not None and row.device_fingerprint != ""


def test_anomaly_review_writes_audit_log(client, app, admin_user):
    from app.models.anomaly_flag import AnomalyFlag
    from app.models.audit_log import AuditLog

    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    with app.app_context():
        admin_id = User.query.filter_by(username="admin").first().id
        flag = AnomalyFlag(
            user_id=admin_id,
            username="admin",
            anomaly_type="TEST_ANOMALY",
            reviewed=False,
            detected_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db.session.add(flag)
        db.session.commit()
        fid = flag.id

    res = client.post(f"/admin/anomalies/{fid}/review", headers={"HX-Request": "true"})
    assert res.status_code == 200

    with app.app_context():
        row = AuditLog.query.filter_by(action="ANOMALY_FLAG_REVIEWED", resource_id=str(fid)).first()
        assert row is not None


# ---------------------------------------------------------------------------
# Delegation scope normalization + effect tests  (audit finding #2 + #4)
# ---------------------------------------------------------------------------

def _reauth_session(client, action_name):
    with client.session_transaction() as sess:
        sess.setdefault("reauth_confirmed", {})
        sess["reauth_confirmed"][action_name] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def test_delegation_scope_shorthand_is_normalized_to_canonical(client, app, admin_user, seeded_assessment):
    """Scope submitted as shorthand 'cohort:42' must be stored as 'scope:cohort:42'."""
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    _reauth_session(client, "create_delegation")

    with app.app_context():
        admin_id = User.query.filter_by(username="admin").first().id
        cohort_id = seeded_assessment["cohort_id"]
        delegate = User(username="norm_test_user", role="faculty_advisor", password_hash="x", is_active=True)
        db.session.add(delegate)
        db.session.commit()
        delegate_id = delegate.id

    res = client.post(
        "/admin/permissions/delegations",
        data={
            "delegator_id": str(admin_id),
            "delegate_id": str(delegate_id),
            "scope": f"cohort:{cohort_id}",
            "permissions": "cohort:view",
            "expires_in_days": "7",
        },
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 200

    with app.app_context():
        d = TemporaryDelegation.query.filter_by(delegate_id=delegate_id).order_by(TemporaryDelegation.id.desc()).first()
        assert d is not None
        assert d.scope == f"scope:cohort:{cohort_id}", (
            f"Expected canonical scope 'scope:cohort:{cohort_id}', got '{d.scope}'"
        )


def test_delegation_invalid_scope_returns_400(client, app, admin_user, seeded_assessment):
    """Submitting a completely unrecognized scope format must return 400 with an error message."""
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    _reauth_session(client, "create_delegation")

    with app.app_context():
        admin_id = User.query.filter_by(username="admin").first().id
        delegate = User(username="bad_scope_user", role="faculty_advisor", password_hash="x", is_active=True)
        db.session.add(delegate)
        db.session.commit()
        delegate_id = delegate.id

    res = client.post(
        "/admin/permissions/delegations",
        data={
            "delegator_id": str(admin_id),
            "delegate_id": str(delegate_id),
            "scope": "INVALID:FORMAT:!!",
            "permissions": "cohort:view",
            "expires_in_days": "7",
        },
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 400
    assert "Invalid scope" in res.get_data(as_text=True)


def test_delegation_grants_access_to_delegated_cohort(client, app, admin_user, seeded_assessment):
    """End-to-end: admin creates delegation for faculty_advisor via route; delegate can
    access the delegated cohort detail page but NOT a cohort outside the scope."""
    from tests.conftest import create_user
    from app.services.auth_service import hash_password

    cohort_id = seeded_assessment["cohort_id"]
    cohort2_id = seeded_assessment["cohort2_id"]

    with app.app_context():
        advisor = create_user("effect_advisor", "faculty_advisor", "Advisor@Practicum1")
        advisor_id = advisor.id
        admin_id = User.query.filter_by(username="admin").first().id

    # Step 1: admin creates delegation with canonical scope
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    _reauth_session(client, "create_delegation")
    res = client.post(
        "/admin/permissions/delegations",
        data={
            "delegator_id": str(admin_id),
            "delegate_id": str(advisor_id),
            "scope": f"scope:cohort:{cohort_id}",
            "permissions": "cohort:view",
            "expires_in_days": "7",
        },
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 200

    # Step 2: login as the advisor (no cohort membership)
    client.get("/logout", follow_redirects=True)
    client.post("/login", data={"username": "effect_advisor", "password": "Advisor@Practicum1"})

    # Step 3: advisor CAN access the delegated cohort
    res_allowed = client.get(f"/cohorts/{cohort_id}", follow_redirects=False)
    assert res_allowed.status_code == 200, (
        f"Advisor with delegated scope:cohort:{cohort_id} must be able to access /cohorts/{cohort_id}"
    )

    # Step 4: advisor CANNOT access a different cohort outside the delegation scope
    res_denied = client.get(f"/cohorts/{cohort2_id}", follow_redirects=False)
    assert res_denied.status_code == 403, (
        f"Advisor must NOT access cohort {cohort2_id} which is outside the delegated scope"
    )


def test_delegation_access_denied_after_expiry(client, app, admin_user, seeded_assessment):
    """A delegation with is_active=False must not grant cohort access."""
    from tests.conftest import create_user
    import json

    cohort_id = seeded_assessment["cohort_id"]

    with app.app_context():
        advisor = create_user("expired_advisor", "faculty_advisor", "Advisor@Practicum1")
        advisor_id = advisor.id
        admin_id = User.query.filter_by(username="admin").first().id

        # Insert an already-expired (is_active=False) delegation directly
        past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
        d = TemporaryDelegation(
            delegator_id=admin_id,
            delegate_id=advisor_id,
            scope=f"scope:cohort:{cohort_id}",
            permissions=json.dumps(["cohort:view"]),
            expires_at=past,
            is_active=False,
        )
        db.session.add(d)
        db.session.commit()

    client.post("/login", data={"username": "expired_advisor", "password": "Advisor@Practicum1"})
    res = client.get(f"/cohorts/{cohort_id}", follow_redirects=False)
    assert res.status_code == 403, "Expired/inactive delegation must not grant cohort access"


# ---------------------------------------------------------------------------
# Anomaly GET read-only + scan POST tests  (audit finding #3)
# ---------------------------------------------------------------------------

def test_get_anomalies_is_side_effect_free(client, app, admin_user):
    """GET /admin/anomalies must not create AnomalyFlag records."""
    from app.models.anomaly_flag import AnomalyFlag

    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})

    with app.app_context():
        before_count = AnomalyFlag.query.count()

    res = client.get("/admin/anomalies")
    assert res.status_code == 200

    with app.app_context():
        after_count = AnomalyFlag.query.count()

    assert before_count == after_count, (
        "GET /admin/anomalies must be side-effect free and must not create AnomalyFlag records"
    )


def test_anomaly_scan_post_creates_flags_and_audit_event(client, app, admin_user):
    """POST /admin/anomalies/scan must create AnomalyFlag records (if any detected) and
    emit an ANOMALY_FLAGS_CREATED audit log entry."""
    from app.models.anomaly_flag import AnomalyFlag
    from app.models.audit_log import AuditLog

    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})

    # Capture the initial count
    with app.app_context():
        before_flag_count = AnomalyFlag.query.count()

    res = client.post("/admin/anomalies/scan", headers={"HX-Request": "true"})
    assert res.status_code == 200

    with app.app_context():
        after_flag_count = AnomalyFlag.query.count()
        new_flags = after_flag_count - before_flag_count

    # If new flags were created, a corresponding audit event must exist
    if new_flags > 0:
        with app.app_context():
            audit_row = AuditLog.query.filter_by(action="ANOMALY_FLAGS_CREATED").first()
            assert audit_row is not None, "ANOMALY_FLAGS_CREATED audit event must be emitted when flags are created"


def test_anomaly_scan_post_requires_dept_admin(client, app, admin_user, student_user):
    """POST /admin/anomalies/scan must be inaccessible to non-admin users."""
    client.post("/login", data={"username": "student1", "password": "Student@Practicum1"})
    res = client.post("/admin/anomalies/scan", follow_redirects=False)
    assert res.status_code in (302, 403)


# ---------------------------------------------------------------------------
# Delegation hierarchy scope API tests (F-002)
# ---------------------------------------------------------------------------


def _create_delegation_via_api(client, app, admin_id, delegate_id, scope):
    """Helper: admin creates a delegation via the API route."""
    _reauth_session(client, "create_delegation")
    return client.post(
        "/admin/permissions/delegations",
        data={
            "delegator_id": str(admin_id),
            "delegate_id": str(delegate_id),
            "scope": scope,
            "permissions": "cohort:view,cohort:grade",
            "expires_in_days": "7",
        },
        headers={"HX-Request": "true"},
    )


def test_api_delegation_scope_school_grants_access(client, app, admin_user, seeded_assessment):
    """Delegation created with scope:school:<id> must grant cohort access to delegate."""
    from tests.conftest import create_user
    from app.models.org import Cohort, Class, Major

    with app.app_context():
        admin_id = User.query.filter_by(username="admin").first().id
        cohort = db.session.get(Cohort, seeded_assessment["cohort_id"])
        klass = db.session.get(Class, cohort.class_id)
        major = db.session.get(Major, klass.major_id)
        school_id = major.school_id
        advisor = create_user("api_school_advisor", "faculty_advisor", "Advisor@Practicum1")
        advisor_id = advisor.id

    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    res = _create_delegation_via_api(client, app, admin_id, advisor_id, f"scope:school:{school_id}")
    assert res.status_code == 200

    client.get("/logout", follow_redirects=True)
    client.post("/login", data={"username": "api_school_advisor", "password": "Advisor@Practicum1"})

    res_ok = client.get(f"/cohorts/{seeded_assessment['cohort_id']}", follow_redirects=False)
    assert res_ok.status_code == 200, "Delegate with scope:school must access cohorts in that school"


def test_api_delegation_scope_school_denies_other_school(client, app, admin_user, seeded_assessment):
    """Delegation with scope:school:<id> must deny cohorts in a different school."""
    from tests.conftest import create_user
    from app.models.org import Cohort, Class, Major, School, Department, SubDepartment

    with app.app_context():
        admin_id = User.query.filter_by(username="admin").first().id
        cohort = db.session.get(Cohort, seeded_assessment["cohort_id"])
        klass = db.session.get(Class, cohort.class_id)
        major = db.session.get(Major, klass.major_id)
        school_id = major.school_id

        # Create cohort in a different school
        school2 = School(name="School API2", code="SA2", is_active=True)
        db.session.add(school2)
        db.session.flush()
        dept2 = Department(school_id=school2.id, name="Dept API2", code="DA2")
        db.session.add(dept2)
        db.session.flush()
        sub2 = SubDepartment(department_id=dept2.id, name="Sub API2", code="SBA2")
        db.session.add(sub2)
        db.session.flush()
        major2 = Major(name="Major API2", code="MA2", school_id=school2.id, sub_department_id=sub2.id)
        db.session.add(major2)
        db.session.flush()
        class2 = Class(name="Class API2", year=2026, major_id=major2.id)
        db.session.add(class2)
        db.session.flush()
        other_cohort = Cohort(name="Cohort API2", class_id=class2.id, internship_term="2026 Spring", is_active=True)
        db.session.add(other_cohort)
        db.session.commit()
        other_cohort_id = other_cohort.id

        advisor = create_user("api_school_deny_adv", "faculty_advisor", "Advisor@Practicum1")
        advisor_id = advisor.id

    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    _create_delegation_via_api(client, app, admin_id, advisor_id, f"scope:school:{school_id}")

    client.get("/logout", follow_redirects=True)
    client.post("/login", data={"username": "api_school_deny_adv", "password": "Advisor@Practicum1"})

    res_denied = client.get(f"/cohorts/{other_cohort_id}", follow_redirects=False)
    assert res_denied.status_code == 403, "Delegate must NOT access cohorts outside delegated school"


def test_api_delegation_scope_subdept_accepted_and_enforced(client, app, admin_user, seeded_assessment):
    """scope:subdept:<id> must be accepted by the delegation creation endpoint and enforced."""
    from tests.conftest import create_user
    from app.models.org import Cohort, Class, Major, SubDepartment

    with app.app_context():
        admin_id = User.query.filter_by(username="admin").first().id
        cohort = db.session.get(Cohort, seeded_assessment["cohort_id"])
        klass = db.session.get(Class, cohort.class_id)
        major = db.session.get(Major, klass.major_id)
        subdept_id = major.sub_department_id
        advisor = create_user("api_subdept_adv", "faculty_advisor", "Advisor@Practicum1")
        advisor_id = advisor.id

    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    res = _create_delegation_via_api(client, app, admin_id, advisor_id, f"scope:subdept:{subdept_id}")
    assert res.status_code == 200, "scope:subdept:<id> must be accepted by delegation endpoint"

    client.get("/logout", follow_redirects=True)
    client.post("/login", data={"username": "api_subdept_adv", "password": "Advisor@Practicum1"})

    res_ok = client.get(f"/cohorts/{seeded_assessment['cohort_id']}", follow_redirects=False)
    assert res_ok.status_code == 200, "Delegate with scope:subdept must access cohorts in that sub-dept"


def test_api_delegation_scope_self_accepted_and_enforced(client, app, admin_user, seeded_assessment):
    """scope:self must be accepted by delegation endpoint; delegate accesses only member cohorts."""
    from tests.conftest import create_user
    from app.models.assignment import CohortMember

    with app.app_context():
        admin_id = User.query.filter_by(username="admin").first().id
        advisor = create_user("api_self_adv", "faculty_advisor", "Advisor@Practicum1")
        advisor_id = advisor.id
        # Make advisor a member of cohort 1 only
        db.session.add(CohortMember(cohort_id=seeded_assessment["cohort_id"], user_id=advisor_id, role_in_cohort="faculty_advisor"))
        db.session.commit()

    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    res = _create_delegation_via_api(client, app, admin_id, advisor_id, "scope:self")
    assert res.status_code == 200, "scope:self must be accepted by delegation endpoint"

    client.get("/logout", follow_redirects=True)
    client.post("/login", data={"username": "api_self_adv", "password": "Advisor@Practicum1"})

    res_ok = client.get(f"/cohorts/{seeded_assessment['cohort_id']}", follow_redirects=False)
    assert res_ok.status_code == 200, "Delegate with scope:self must access member cohort"

    res_denied = client.get(f"/cohorts/{seeded_assessment['cohort2_id']}", follow_redirects=False)
    assert res_denied.status_code == 403, "Delegate with scope:self must NOT access non-member cohort"


def test_api_delegation_scope_dept_shorthand_accepted(client, app, admin_user, seeded_assessment):
    """Shorthand 'dept' must be normalized to 'scope:dept' and accepted."""
    from tests.conftest import create_user

    with app.app_context():
        admin_id = User.query.filter_by(username="admin").first().id
        advisor = create_user("api_dept_short_adv", "faculty_advisor", "Advisor@Practicum1")
        advisor_id = advisor.id

    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    res = _create_delegation_via_api(client, app, admin_id, advisor_id, "dept")
    assert res.status_code == 200, "Shorthand 'dept' must be normalized and accepted"

    with app.app_context():
        d = TemporaryDelegation.query.filter_by(delegate_id=advisor_id).order_by(TemporaryDelegation.id.desc()).first()
        assert d.scope == "scope:dept", f"Expected 'scope:dept', got '{d.scope}'"


def test_api_delegation_scope_dept_enforced_across_departments(client, app, admin_user, seeded_assessment):
    """Delegation with scope:dept must allow same department and deny different department cohorts."""
    from tests.conftest import create_user
    from app.models.assignment import CohortMember
    from app.models.org import Cohort, Class, Major, School, Department, SubDepartment

    with app.app_context():
        admin_id = User.query.filter_by(username="admin").first().id

        # Seeded cohorts share the same department tree in the fixture.
        allowed_cohort_id = seeded_assessment["cohort_id"]
        member_cohort_id = seeded_assessment["cohort2_id"]

        # Create a cohort under a different department tree.
        school2 = School(name="Dept Scope School 2", code="DSS2", is_active=True)
        db.session.add(school2)
        db.session.flush()
        dept2 = Department(school_id=school2.id, name="Dept Scope Dept 2", code="DSD2")
        db.session.add(dept2)
        db.session.flush()
        sub2 = SubDepartment(department_id=dept2.id, name="Dept Scope Sub 2", code="DSSUB2")
        db.session.add(sub2)
        db.session.flush()
        major2 = Major(name="Dept Scope Major 2", code="DSM2", school_id=school2.id, sub_department_id=sub2.id)
        db.session.add(major2)
        db.session.flush()
        class2 = Class(name="Dept Scope Class 2", year=2026, major_id=major2.id)
        db.session.add(class2)
        db.session.flush()
        denied_cohort = Cohort(name="Dept Scope Cohort 2", class_id=class2.id, internship_term="2026 Spring", is_active=True)
        db.session.add(denied_cohort)
        db.session.commit()
        denied_cohort_id = denied_cohort.id

        advisor = create_user("api_dept_enforce_adv", "faculty_advisor", "Advisor@Practicum1")
        advisor_id = advisor.id
        # Give advisor one cohort membership in the target department so scope:dept
        # can expand to sibling cohorts in that same department tree.
        db.session.add(
            CohortMember(
                cohort_id=member_cohort_id,
                user_id=advisor_id,
                role_in_cohort="faculty_advisor",
            )
        )
        db.session.commit()

    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    res = _create_delegation_via_api(client, app, admin_id, advisor_id, "scope:dept")
    assert res.status_code == 200

    client.get("/logout", follow_redirects=True)
    client.post("/login", data={"username": "api_dept_enforce_adv", "password": "Advisor@Practicum1"})

    res_ok = client.get(f"/cohorts/{allowed_cohort_id}", follow_redirects=False)
    assert res_ok.status_code == 200, "Delegate with scope:dept must access cohorts in delegate's department tree"

    res_denied = client.get(f"/cohorts/{denied_cohort_id}", follow_redirects=False)
    assert res_denied.status_code == 403, "Delegate with scope:dept must NOT access cohorts in a different department tree"


def test_api_delegation_scope_class_enforced(client, app, admin_user, seeded_assessment):
    """Delegation with scope:class:<id> must grant access to cohorts under that class only."""
    from tests.conftest import create_user
    from app.models.org import Cohort, Class, Major

    with app.app_context():
        admin_id = User.query.filter_by(username="admin").first().id
        cohort = db.session.get(Cohort, seeded_assessment["cohort_id"])
        class_id = cohort.class_id

        # Create a cohort in a different class
        klass = db.session.get(Class, class_id)
        class2 = Class(name="Class API3", year=2026, major_id=klass.major_id)
        db.session.add(class2)
        db.session.flush()
        other_cohort = Cohort(name="Cohort API3", class_id=class2.id, internship_term="2026 Spring", is_active=True)
        db.session.add(other_cohort)
        db.session.commit()
        other_cohort_id = other_cohort.id

        advisor = create_user("api_class_adv", "faculty_advisor", "Advisor@Practicum1")
        advisor_id = advisor.id

    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    res = _create_delegation_via_api(client, app, admin_id, advisor_id, f"scope:class:{class_id}")
    assert res.status_code == 200

    client.get("/logout", follow_redirects=True)
    client.post("/login", data={"username": "api_class_adv", "password": "Advisor@Practicum1"})

    res_ok = client.get(f"/cohorts/{seeded_assessment['cohort_id']}", follow_redirects=False)
    assert res_ok.status_code == 200, "Delegate with scope:class must access cohorts in that class"

    res_denied = client.get(f"/cohorts/{other_cohort_id}", follow_redirects=False)
    assert res_denied.status_code == 403, "Delegate with scope:class must NOT access cohorts in other class"
