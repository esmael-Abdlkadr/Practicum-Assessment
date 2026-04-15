"""Top-6 gap tests for rbac_service functions not covered elsewhere."""
from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.models.assignment import CohortMember
from app.models.permission import TemporaryDelegation, UserPermission
from app.models.user import User
from app.services import rbac_service
from app.services.auth_service import hash_password


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _make_user(username, role="faculty_advisor"):
    u = User(username=username, password_hash=hash_password("Test1234!@Ab"), role=role, is_active=True)
    db.session.add(u)
    db.session.flush()
    return u


# ---------------------------------------------------------------------------
# GAP-1: expired UserPermission rows must NOT appear in get_user_permissions
# ---------------------------------------------------------------------------

def test_expired_user_permission_is_excluded(app, seeded_assessment):
    """An explicit UserPermission with expires_at in the past must not be returned.

    Use role=student so the base ROLE_PERMISSIONS don't already include cohort:grade;
    only the (expired) explicit grant would add it.
    """
    with app.app_context():
        u = _make_user("expired_perm_user", role="student")
        past = _now() - timedelta(hours=1)
        db.session.add(UserPermission(user_id=u.id, permission="cohort:grade", expires_at=past))
        db.session.commit()

        perms = rbac_service.get_user_permissions(u)
        assert "cohort:grade" not in perms


# ---------------------------------------------------------------------------
# GAP-2: active delegation permissions ARE included in get_user_permissions
# ---------------------------------------------------------------------------

def test_active_delegation_permissions_included(app, seeded_assessment):
    """Active, non-expired delegation permissions must appear in get_user_permissions."""
    with app.app_context():
        admin = User.query.filter_by(username="admin").first()
        u = _make_user("deleg_perm_user")
        delegation = TemporaryDelegation(
            delegator_id=admin.id,
            delegate_id=u.id,
            scope="scope:global",
            permissions='["report:export"]',
            expires_at=_now() + timedelta(days=1),
            is_active=True,
        )
        db.session.add(delegation)
        db.session.commit()

        perms = rbac_service.get_user_permissions(u)
        assert "report:export" in perms


# ---------------------------------------------------------------------------
# GAP-3: inactive delegation (is_active=False) must NOT grant cohort access
# ---------------------------------------------------------------------------

def test_inactive_delegation_does_not_grant_access(app, seeded_assessment):
    """A revoked (is_active=False) delegation must not allow cohort access."""
    with app.app_context():
        admin = User.query.filter_by(username="admin").first()
        u = _make_user("revoked_deleg_user")
        cid = seeded_assessment["cohort_id"]
        delegation = TemporaryDelegation(
            delegator_id=admin.id,
            delegate_id=u.id,
            scope=f"scope:cohort:{cid}",
            permissions='["cohort:view"]',
            expires_at=_now() + timedelta(days=7),
            is_active=False,  # explicitly revoked
        )
        db.session.add(delegation)
        db.session.commit()

        assert rbac_service.can_access_cohort(u, cid) is False


# ---------------------------------------------------------------------------
# GAP-4: get_delegation_cohort_ids returns empty set when no active delegations
# ---------------------------------------------------------------------------

def test_get_delegation_cohort_ids_no_delegations_returns_empty_set(app, seeded_assessment):
    """A user with no active delegations should get an empty set, not None."""
    with app.app_context():
        u = _make_user("no_deleg_user")
        db.session.commit()

        result = rbac_service.get_delegation_cohort_ids(u)
        assert result == set()
        assert result is not None


# ---------------------------------------------------------------------------
# GAP-5: get_available_roles returns primary role + extra role: permissions
# ---------------------------------------------------------------------------

def test_get_available_roles_includes_extra_role_permissions(app, seeded_assessment):
    """get_available_roles must include roles granted via role:<name> UserPermission."""
    with app.app_context():
        u = _make_user("multi_role_user", role="faculty_advisor")
        db.session.add(UserPermission(user_id=u.id, permission="role:corporate_mentor"))
        db.session.commit()

        roles = rbac_service.get_available_roles(u)
        assert "faculty_advisor" in roles
        assert "corporate_mentor" in roles


def test_get_available_roles_no_extras_returns_only_primary(app, seeded_assessment):
    """Without extra role: permissions, only the primary role is returned."""
    with app.app_context():
        u = _make_user("single_role_user", role="student")
        db.session.commit()

        roles = rbac_service.get_available_roles(u)
        assert roles == ["student"]


# ---------------------------------------------------------------------------
# GAP-6: can_access_student — students can only access themselves;
#         faculty can only access students in shared cohorts
# ---------------------------------------------------------------------------

def test_student_can_access_own_record(app, seeded_assessment):
    """A student can access their own student record."""
    with app.app_context():
        student = User.query.filter_by(username="student1").first()
        assert rbac_service.can_access_student(student, student.id) is True


def test_student_cannot_access_other_student(app, seeded_assessment):
    """A student must NOT access another student's record."""
    with app.app_context():
        student = User.query.filter_by(username="student1").first()
        student2 = User.query.filter_by(username="student2").first()
        assert rbac_service.can_access_student(student, student2.id) is False


def test_faculty_can_access_student_in_shared_cohort(app, seeded_assessment):
    """A faculty advisor can access a student who is in one of their cohorts."""
    with app.app_context():
        advisor = User.query.filter_by(username="advisor1").first()
        student = User.query.filter_by(username="student1").first()
        # advisor and student are both in cohort_id from seeded_assessment
        assert rbac_service.can_access_student(advisor, student.id) is True


def test_faculty_cannot_access_student_in_different_cohort(app, seeded_assessment):
    """A faculty advisor must NOT access a student not in any shared cohort."""
    with app.app_context():
        advisor = User.query.filter_by(username="advisor1").first()
        student2 = User.query.filter_by(username="student2").first()
        # advisor is only in cohort_id; student2 is only in cohort2_id
        assert rbac_service.can_access_student(advisor, student2.id) is False
