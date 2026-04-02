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
