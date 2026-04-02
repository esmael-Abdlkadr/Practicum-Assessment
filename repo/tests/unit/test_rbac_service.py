from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models.org import Class, Cohort, Major
from app.models.permission import TemporaryDelegation, UserPermission
from app.models.user import User
from app.services.auth_service import hash_password
from app.services import rbac_service


def test_can_access_cohort_assigned_faculty_true(app, seeded_assessment):
    with app.app_context():
        faculty = User.query.filter_by(username="advisor1").first()
        assert rbac_service.can_access_cohort(faculty, seeded_assessment["cohort_id"]) is True


def test_can_access_cohort_unassigned_faculty_false(app, seeded_assessment):
    with app.app_context():
        faculty = User.query.filter_by(username="advisor1").first()
        assert rbac_service.can_access_cohort(faculty, seeded_assessment["cohort2_id"]) is False


def test_get_accessible_cohorts_student_only_own(app, seeded_assessment):
    with app.app_context():
        student = User.query.filter_by(username="student1").first()
        cohorts = rbac_service.get_accessible_cohorts(student)
        assert len(cohorts) == 1
        assert cohorts[0].id == seeded_assessment["cohort_id"]


def test_expire_delegations_marks_inactive(app, seeded_assessment):
    with app.app_context():
        admin = User.query.filter_by(username="admin").first()
        faculty = User.query.filter_by(username="advisor1").first()
        d = TemporaryDelegation(
            delegator_id=admin.id,
            delegate_id=faculty.id,
            scope="cohort:1",
            permissions='["cohort:view"]',
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1),
            is_active=True,
        )
        db.session.add(d)
        db.session.commit()
        changed = rbac_service.expire_delegations()
        assert changed >= 1
        assert db.session.get(TemporaryDelegation, d.id).is_active is False


def test_scope_school_grants_cohort_access(app, seeded_assessment):
    """scope:school:<id> permission grants access to all cohorts in that school."""
    with app.app_context():
        cohort_id = seeded_assessment["cohort_id"]
        cohort = db.session.get(Cohort, cohort_id)
        klass = db.session.get(Class, cohort.class_id)
        major = db.session.get(Major, klass.major_id)
        school_id = major.school_id

        user = User(
            username="scope_test_faculty",
            password_hash=hash_password("Test1234!@Ab"),
            role="faculty_advisor",
        )
        db.session.add(user)
        db.session.flush()

        perm = UserPermission(
            user_id=user.id,
            permission=f"scope:school:{school_id}",
        )
        db.session.add(perm)
        db.session.commit()

        assert rbac_service.can_access_cohort(user, cohort_id) is True
        cohorts = rbac_service.get_accessible_cohorts(user)
        assert any(c.id == cohort_id for c in cohorts)


def test_scope_global_grants_all_cohorts(app, seeded_assessment):
    """scope:global grants access to every cohort."""
    with app.app_context():
        user = User(
            username="scope_global_faculty",
            password_hash=hash_password("Test1234!@Ab"),
            role="faculty_advisor",
        )
        db.session.add(user)
        db.session.flush()
        db.session.add(UserPermission(user_id=user.id, permission="scope:global"))
        db.session.commit()

        all_cohorts = rbac_service.get_accessible_cohorts(user)
        assert len(all_cohorts) >= 1


def test_no_scope_no_membership_blocks_cohort_access(app, seeded_assessment):
    """A user with no scope permissions and no membership cannot access a cohort."""
    with app.app_context():
        user = User(
            username="no_scope_faculty",
            password_hash=hash_password("Test1234!@Ab"),
            role="faculty_advisor",
        )
        db.session.add(user)
        db.session.commit()

        assert rbac_service.can_access_cohort(user, seeded_assessment["cohort_id"]) is False
        assert rbac_service.get_accessible_cohorts(user) == []


def test_delegation_scope_cohort_allows_specified_cohort(app, seeded_assessment):
    with app.app_context():
        user = User(
            username="deleg_scope_allow",
            password_hash=hash_password("Test1234!@Ab"),
            role="faculty_advisor",
        )
        db.session.add(user)
        db.session.flush()

        delegation = TemporaryDelegation(
            delegator_id=seeded_assessment["admin_id"],
            delegate_id=user.id,
            scope=f"scope:cohort:{seeded_assessment['cohort_id']}",
            permissions='["cohort:view"]',
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1),
            is_active=True,
        )
        db.session.add(delegation)
        db.session.commit()

        assert rbac_service.can_access_cohort(user, seeded_assessment["cohort_id"]) is True


def test_delegation_scope_cohort_denies_other_cohort(app, seeded_assessment):
    with app.app_context():
        user = User(
            username="deleg_scope_deny",
            password_hash=hash_password("Test1234!@Ab"),
            role="faculty_advisor",
        )
        db.session.add(user)
        db.session.flush()

        delegation = TemporaryDelegation(
            delegator_id=seeded_assessment["admin_id"],
            delegate_id=user.id,
            scope=f"scope:cohort:{seeded_assessment['cohort_id']}",
            permissions='["cohort:view"]',
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1),
            is_active=True,
        )
        db.session.add(delegation)
        db.session.commit()

        assert rbac_service.can_access_cohort(user, seeded_assessment["cohort2_id"]) is False


def test_delegation_scope_global_allows_all_cohorts(app, seeded_assessment):
    with app.app_context():
        user = User(
            username="deleg_scope_global",
            password_hash=hash_password("Test1234!@Ab"),
            role="faculty_advisor",
        )
        db.session.add(user)
        db.session.flush()

        delegation = TemporaryDelegation(
            delegator_id=seeded_assessment["admin_id"],
            delegate_id=user.id,
            scope="scope:global",
            permissions='["cohort:view"]',
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1),
            is_active=True,
        )
        db.session.add(delegation)
        db.session.commit()

        assert rbac_service.can_access_cohort(user, seeded_assessment["cohort_id"]) is True
