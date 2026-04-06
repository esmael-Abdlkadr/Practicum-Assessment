from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models.assignment import CohortMember
from app.models.org import Class, Cohort, Department, Major, School, SubDepartment
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


def test_legacy_shorthand_delegation_scope_is_normalized(app, seeded_assessment):
    """Legacy delegation rows like 'cohort:<id>' must still grant access."""
    with app.app_context():
        user = User(
            username="legacy_deleg_scope",
            password_hash=hash_password("Test1234!@Ab"),
            role="faculty_advisor",
        )
        db.session.add(user)
        db.session.flush()

        delegation = TemporaryDelegation(
            delegator_id=seeded_assessment["admin_id"],
            delegate_id=user.id,
            scope=f"cohort:{seeded_assessment['cohort_id']}",  # legacy shorthand
            permissions='["cohort:view"]',
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1),
            is_active=True,
        )
        db.session.add(delegation)
        db.session.commit()

        assert rbac_service.can_access_cohort(user, seeded_assessment["cohort_id"]) is True


# ---------------------------------------------------------------------------
#  resolve_scope tests
# ---------------------------------------------------------------------------


def test_resolve_scope_global_returns_all(app, seeded_assessment):
    """scope:global resolves to every active cohort."""
    with app.app_context():
        all_cohorts = Cohort.query.filter(Cohort.is_active.is_(True)).all()
        user = User.query.filter_by(username="advisor1").first()
        result = rbac_service.resolve_scope(user, {"scope:global"})
        assert result == {c.id for c in all_cohorts}


def test_resolve_scope_self_returns_member_cohorts(app, seeded_assessment):
    """scope:self resolves to only the cohorts where the user is a member."""
    with app.app_context():
        student = User.query.filter_by(username="student1").first()
        result = rbac_service.resolve_scope(student, {"scope:self"})
        assert result == {seeded_assessment["cohort_id"]}


def test_resolve_scope_cohort_returns_specific(app, seeded_assessment):
    """scope:cohort:<id> resolves to just that cohort."""
    with app.app_context():
        user = User.query.filter_by(username="advisor1").first()
        cid = seeded_assessment["cohort_id"]
        result = rbac_service.resolve_scope(user, {f"scope:cohort:{cid}"})
        assert result == {cid}


def test_resolve_scope_dept_includes_subdepartments(app, seeded_assessment):
    """scope:dept resolves to all cohorts under the user's department tree."""
    with app.app_context():
        cohort = db.session.get(Cohort, seeded_assessment["cohort_id"])
        klass = db.session.get(Class, cohort.class_id)
        major = db.session.get(Major, klass.major_id)
        subdept = db.session.get(SubDepartment, major.sub_department_id)
        dept = db.session.get(Department, subdept.department_id)

        sub2 = SubDepartment(department_id=dept.id, name="Sub2", code="S2")
        db.session.add(sub2)
        db.session.flush()
        school = db.session.get(School, major.school_id)
        major2 = Major(name="Major2", code="M2", school_id=school.id, sub_department_id=sub2.id)
        db.session.add(major2)
        db.session.flush()
        class2 = Class(name="Class2", year=2026, major_id=major2.id)
        db.session.add(class2)
        db.session.flush()
        cohort_new = Cohort(name="Cohort Dept2", class_id=class2.id, internship_term="2026 Spring", is_active=True)
        db.session.add(cohort_new)
        db.session.flush()

        user = User(username="dept_scope_user", password_hash=hash_password("Test1234!@Ab"), role="faculty_advisor")
        db.session.add(user)
        db.session.flush()
        db.session.add(CohortMember(cohort_id=seeded_assessment["cohort_id"], user_id=user.id, role_in_cohort="faculty_advisor"))
        db.session.add(UserPermission(user_id=user.id, permission="scope:dept"))
        db.session.commit()

        result = rbac_service.resolve_scope(user, {"scope:dept"})
        assert seeded_assessment["cohort_id"] in result
        assert cohort_new.id in result


def test_resolve_scope_subdept(app, seeded_assessment):
    """scope:subdept:<id> resolves to cohorts under that sub-department only."""
    with app.app_context():
        cohort = db.session.get(Cohort, seeded_assessment["cohort_id"])
        klass = db.session.get(Class, cohort.class_id)
        major = db.session.get(Major, klass.major_id)
        subdept_id = major.sub_department_id

        user = User(username="subdept_scope_user", password_hash=hash_password("Test1234!@Ab"), role="faculty_advisor")
        db.session.add(user)
        db.session.flush()
        db.session.add(UserPermission(user_id=user.id, permission=f"scope:subdept:{subdept_id}"))
        db.session.commit()

        result = rbac_service.resolve_scope(user, {f"scope:subdept:{subdept_id}"})
        assert seeded_assessment["cohort_id"] in result
        assert seeded_assessment["cohort2_id"] in result


def test_scope_subdept_grants_cohort_access(app, seeded_assessment):
    """scope:subdept:<id> via UserPermission grants cohort access through can_access_cohort."""
    with app.app_context():
        cohort = db.session.get(Cohort, seeded_assessment["cohort_id"])
        klass = db.session.get(Class, cohort.class_id)
        major = db.session.get(Major, klass.major_id)
        subdept_id = major.sub_department_id

        user = User(username="subdept_access_user", password_hash=hash_password("Test1234!@Ab"), role="faculty_advisor")
        db.session.add(user)
        db.session.flush()
        db.session.add(UserPermission(user_id=user.id, permission=f"scope:subdept:{subdept_id}"))
        db.session.commit()

        assert rbac_service.can_access_cohort(user, seeded_assessment["cohort_id"]) is True


def test_scope_self_grants_own_cohort_access(app, seeded_assessment):
    """scope:self via UserPermission grants access to cohorts user is a member of."""
    with app.app_context():
        user = User(username="self_scope_user", password_hash=hash_password("Test1234!@Ab"), role="faculty_advisor")
        db.session.add(user)
        db.session.flush()
        db.session.add(CohortMember(cohort_id=seeded_assessment["cohort_id"], user_id=user.id, role_in_cohort="faculty_advisor"))
        db.session.add(UserPermission(user_id=user.id, permission="scope:self"))
        db.session.commit()

        assert rbac_service.can_access_cohort(user, seeded_assessment["cohort_id"]) is True
        assert rbac_service.can_access_cohort(user, seeded_assessment["cohort2_id"]) is False


def test_scope_dept_denies_cross_department(app, seeded_assessment):
    """scope:dept must NOT grant access to cohorts in a different department."""
    with app.app_context():
        school2 = School(name="Other School", code="OS", is_active=True)
        db.session.add(school2)
        db.session.flush()
        dept2 = Department(school_id=school2.id, name="Other Dept", code="OD")
        db.session.add(dept2)
        db.session.flush()
        sub2 = SubDepartment(department_id=dept2.id, name="Other Sub", code="OSUB")
        db.session.add(sub2)
        db.session.flush()
        major2 = Major(name="Other Major", code="OM", school_id=school2.id, sub_department_id=sub2.id)
        db.session.add(major2)
        db.session.flush()
        class2 = Class(name="Other Class", year=2026, major_id=major2.id)
        db.session.add(class2)
        db.session.flush()
        other_cohort = Cohort(name="Other Cohort", class_id=class2.id, internship_term="2026 Spring", is_active=True)
        db.session.add(other_cohort)
        db.session.flush()

        user = User(username="cross_dept_user", password_hash=hash_password("Test1234!@Ab"), role="faculty_advisor")
        db.session.add(user)
        db.session.flush()
        db.session.add(CohortMember(cohort_id=seeded_assessment["cohort_id"], user_id=user.id, role_in_cohort="faculty_advisor"))
        db.session.add(UserPermission(user_id=user.id, permission="scope:dept"))
        db.session.commit()

        assert rbac_service.can_access_cohort(user, seeded_assessment["cohort_id"]) is True
        assert rbac_service.can_access_cohort(user, other_cohort.id) is False


def test_resolve_scope_empty_scopes_returns_empty(app, seeded_assessment):
    """Empty scope set returns no cohort IDs."""
    with app.app_context():
        user = User.query.filter_by(username="advisor1").first()
        result = rbac_service.resolve_scope(user, set())
        assert result == set()


# ---------------------------------------------------------------------------
#  Delegation scope hierarchy tests (F-002)
# ---------------------------------------------------------------------------


def _make_delegated_user(app, username, seeded_assessment, scope, member_cohort_id=None):
    """Create a user with a single active delegation of the given scope.

    Returns the user ID (not the ORM object) to avoid DetachedInstanceError.
    Callers must re-query the User inside their own ``app.app_context()``.
    """
    with app.app_context():
        user = User(username=username, password_hash=hash_password("Test1234!@Ab"), role="faculty_advisor")
        db.session.add(user)
        db.session.flush()
        if member_cohort_id:
            db.session.add(CohortMember(cohort_id=member_cohort_id, user_id=user.id, role_in_cohort="faculty_advisor"))
        delegation = TemporaryDelegation(
            delegator_id=seeded_assessment["admin_id"],
            delegate_id=user.id,
            scope=scope,
            permissions='["cohort:view","cohort:grade"]',
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1),
            is_active=True,
        )
        db.session.add(delegation)
        db.session.commit()
        return user.id


def _get_org_ids(app, cohort_id):
    """Return (school_id, dept_id, subdept_id, major_id, class_id) for a cohort."""
    with app.app_context():
        cohort = db.session.get(Cohort, cohort_id)
        klass = db.session.get(Class, cohort.class_id)
        major = db.session.get(Major, klass.major_id)
        subdept = db.session.get(SubDepartment, major.sub_department_id)
        return {
            "school_id": major.school_id,
            "dept_id": subdept.department_id,
            "subdept_id": subdept.id,
            "major_id": major.id,
            "class_id": klass.id,
        }


def test_delegation_scope_school_allows_cohort(app, seeded_assessment):
    """Delegation with scope:school:<id> must grant access to cohorts in that school."""
    org = _get_org_ids(app, seeded_assessment["cohort_id"])
    uid = _make_delegated_user(app, "deleg_school_allow", seeded_assessment, f"scope:school:{org['school_id']}")
    with app.app_context():
        user = db.session.get(User, uid)
        assert rbac_service.can_access_cohort(user, seeded_assessment["cohort_id"]) is True
        assert rbac_service.can_access_cohort(user, seeded_assessment["cohort2_id"]) is True


def test_delegation_scope_school_denies_other_school(app, seeded_assessment):
    """Delegation with scope:school:<id> must deny cohorts in a different school."""
    with app.app_context():
        school2 = School(name="Other School D", code="OSD", is_active=True)
        db.session.add(school2)
        db.session.flush()
        dept2 = Department(school_id=school2.id, name="Dept D", code="DD")
        db.session.add(dept2)
        db.session.flush()
        sub2 = SubDepartment(department_id=dept2.id, name="Sub D", code="SD")
        db.session.add(sub2)
        db.session.flush()
        major2 = Major(name="Major D", code="MD", school_id=school2.id, sub_department_id=sub2.id)
        db.session.add(major2)
        db.session.flush()
        class2 = Class(name="Class D", year=2026, major_id=major2.id)
        db.session.add(class2)
        db.session.flush()
        other_cohort = Cohort(name="Cohort D", class_id=class2.id, internship_term="2026 Spring", is_active=True)
        db.session.add(other_cohort)
        db.session.commit()
        other_cohort_id = other_cohort.id

    org = _get_org_ids(app, seeded_assessment["cohort_id"])
    uid = _make_delegated_user(app, "deleg_school_deny", seeded_assessment, f"scope:school:{org['school_id']}")
    with app.app_context():
        user = db.session.get(User, uid)
        assert rbac_service.can_access_cohort(user, other_cohort_id) is False


def test_delegation_scope_major_allows_cohort(app, seeded_assessment):
    """Delegation with scope:major:<id> must grant access to cohorts under that major."""
    org = _get_org_ids(app, seeded_assessment["cohort_id"])
    uid = _make_delegated_user(app, "deleg_major_allow", seeded_assessment, f"scope:major:{org['major_id']}")
    with app.app_context():
        user = db.session.get(User, uid)
        assert rbac_service.can_access_cohort(user, seeded_assessment["cohort_id"]) is True


def test_delegation_scope_major_denies_other_major(app, seeded_assessment):
    """Delegation with scope:major:<id> must deny cohorts under a different major."""
    with app.app_context():
        org = _get_org_ids(app, seeded_assessment["cohort_id"])
        major2 = Major(name="Major X", code="MX", school_id=org["school_id"], sub_department_id=org["subdept_id"])
        db.session.add(major2)
        db.session.flush()
        class2 = Class(name="Class X", year=2026, major_id=major2.id)
        db.session.add(class2)
        db.session.flush()
        other_cohort = Cohort(name="Cohort X", class_id=class2.id, internship_term="2026 Spring", is_active=True)
        db.session.add(other_cohort)
        db.session.commit()
        other_cohort_id = other_cohort.id

    org = _get_org_ids(app, seeded_assessment["cohort_id"])
    uid = _make_delegated_user(app, "deleg_major_deny", seeded_assessment, f"scope:major:{org['major_id']}")
    with app.app_context():
        user = db.session.get(User, uid)
        assert rbac_service.can_access_cohort(user, seeded_assessment["cohort_id"]) is True
        assert rbac_service.can_access_cohort(user, other_cohort_id) is False


def test_delegation_scope_class_allows_cohort(app, seeded_assessment):
    """Delegation with scope:class:<id> must grant access to cohorts under that class."""
    org = _get_org_ids(app, seeded_assessment["cohort_id"])
    uid = _make_delegated_user(app, "deleg_class_allow", seeded_assessment, f"scope:class:{org['class_id']}")
    with app.app_context():
        user = db.session.get(User, uid)
        assert rbac_service.can_access_cohort(user, seeded_assessment["cohort_id"]) is True
        assert rbac_service.can_access_cohort(user, seeded_assessment["cohort2_id"]) is True


def test_delegation_scope_class_denies_other_class(app, seeded_assessment):
    """Delegation with scope:class:<id> must deny cohorts under a different class."""
    with app.app_context():
        org = _get_org_ids(app, seeded_assessment["cohort_id"])
        class2 = Class(name="Class Y", year=2026, major_id=org["major_id"])
        db.session.add(class2)
        db.session.flush()
        other_cohort = Cohort(name="Cohort Y", class_id=class2.id, internship_term="2026 Spring", is_active=True)
        db.session.add(other_cohort)
        db.session.commit()
        other_cohort_id = other_cohort.id

    org = _get_org_ids(app, seeded_assessment["cohort_id"])
    uid = _make_delegated_user(app, "deleg_class_deny", seeded_assessment, f"scope:class:{org['class_id']}")
    with app.app_context():
        user = db.session.get(User, uid)
        assert rbac_service.can_access_cohort(user, seeded_assessment["cohort_id"]) is True
        assert rbac_service.can_access_cohort(user, other_cohort_id) is False


def test_delegation_scope_subdept_allows_cohort(app, seeded_assessment):
    """Delegation with scope:subdept:<id> must grant access to cohorts under that sub-department."""
    org = _get_org_ids(app, seeded_assessment["cohort_id"])
    uid = _make_delegated_user(app, "deleg_subdept_allow", seeded_assessment, f"scope:subdept:{org['subdept_id']}")
    with app.app_context():
        user = db.session.get(User, uid)
        assert rbac_service.can_access_cohort(user, seeded_assessment["cohort_id"]) is True
        assert rbac_service.can_access_cohort(user, seeded_assessment["cohort2_id"]) is True


def test_delegation_scope_subdept_denies_other_subdept(app, seeded_assessment):
    """Delegation with scope:subdept:<id> must deny cohorts under a different sub-department."""
    with app.app_context():
        org = _get_org_ids(app, seeded_assessment["cohort_id"])
        sub2 = SubDepartment(department_id=org["dept_id"], name="Sub Z", code="SZ")
        db.session.add(sub2)
        db.session.flush()
        major2 = Major(name="Major Z", code="MZ", school_id=org["school_id"], sub_department_id=sub2.id)
        db.session.add(major2)
        db.session.flush()
        class2 = Class(name="Class Z", year=2026, major_id=major2.id)
        db.session.add(class2)
        db.session.flush()
        other_cohort = Cohort(name="Cohort Z", class_id=class2.id, internship_term="2026 Spring", is_active=True)
        db.session.add(other_cohort)
        db.session.commit()
        other_cohort_id = other_cohort.id

    org = _get_org_ids(app, seeded_assessment["cohort_id"])
    uid = _make_delegated_user(app, "deleg_subdept_deny", seeded_assessment, f"scope:subdept:{org['subdept_id']}")
    with app.app_context():
        user = db.session.get(User, uid)
        assert rbac_service.can_access_cohort(user, seeded_assessment["cohort_id"]) is True
        assert rbac_service.can_access_cohort(user, other_cohort_id) is False


def test_delegation_scope_dept_allows_cohort(app, seeded_assessment):
    """Delegation with scope:dept must grant access to cohorts in the delegate's department."""
    uid = _make_delegated_user(
        app, "deleg_dept_allow", seeded_assessment, "scope:dept",
        member_cohort_id=seeded_assessment["cohort_id"],
    )
    with app.app_context():
        user = db.session.get(User, uid)
        assert rbac_service.can_access_cohort(user, seeded_assessment["cohort_id"]) is True
        assert rbac_service.can_access_cohort(user, seeded_assessment["cohort2_id"]) is True


def test_delegation_scope_dept_denies_other_dept(app, seeded_assessment):
    """Delegation with scope:dept must deny cohorts in a different department."""
    with app.app_context():
        school2 = School(name="Other School E", code="OSE", is_active=True)
        db.session.add(school2)
        db.session.flush()
        dept2 = Department(school_id=school2.id, name="Dept E", code="DE")
        db.session.add(dept2)
        db.session.flush()
        sub2 = SubDepartment(department_id=dept2.id, name="Sub E", code="SE")
        db.session.add(sub2)
        db.session.flush()
        major2 = Major(name="Major E", code="ME", school_id=school2.id, sub_department_id=sub2.id)
        db.session.add(major2)
        db.session.flush()
        class2 = Class(name="Class E", year=2026, major_id=major2.id)
        db.session.add(class2)
        db.session.flush()
        other_cohort = Cohort(name="Cohort E", class_id=class2.id, internship_term="2026 Spring", is_active=True)
        db.session.add(other_cohort)
        db.session.commit()
        other_cohort_id = other_cohort.id

    uid = _make_delegated_user(
        app, "deleg_dept_deny", seeded_assessment, "scope:dept",
        member_cohort_id=seeded_assessment["cohort_id"],
    )
    with app.app_context():
        user = db.session.get(User, uid)
        assert rbac_service.can_access_cohort(user, seeded_assessment["cohort_id"]) is True
        assert rbac_service.can_access_cohort(user, other_cohort_id) is False


def test_delegation_scope_self_allows_member_cohort(app, seeded_assessment):
    """Delegation with scope:self must grant access only to cohorts the delegate is a member of."""
    uid = _make_delegated_user(
        app, "deleg_self_allow", seeded_assessment, "scope:self",
        member_cohort_id=seeded_assessment["cohort_id"],
    )
    with app.app_context():
        user = db.session.get(User, uid)
        assert rbac_service.can_access_cohort(user, seeded_assessment["cohort_id"]) is True


def test_delegation_scope_self_denies_non_member_cohort(app, seeded_assessment):
    """Delegation with scope:self must deny cohorts the delegate is NOT a member of."""
    uid = _make_delegated_user(
        app, "deleg_self_deny", seeded_assessment, "scope:self",
        member_cohort_id=seeded_assessment["cohort_id"],
    )
    with app.app_context():
        user = db.session.get(User, uid)
        assert rbac_service.can_access_cohort(user, seeded_assessment["cohort2_id"]) is False


def test_get_delegation_cohort_ids_returns_resolved_hierarchy(app, seeded_assessment):
    """get_delegation_cohort_ids must return cohort IDs for non-cohort scope types."""
    org = _get_org_ids(app, seeded_assessment["cohort_id"])
    uid = _make_delegated_user(app, "deleg_resolve_test", seeded_assessment, f"scope:school:{org['school_id']}")
    with app.app_context():
        user = db.session.get(User, uid)
        ids = rbac_service.get_delegation_cohort_ids(user)
        assert ids is not None
        assert seeded_assessment["cohort_id"] in ids
        assert seeded_assessment["cohort2_id"] in ids
