import json
from datetime import datetime, timezone

from app.extensions import db
from app.models.assignment import CohortMember
from app.models.org import Class, Cohort, Major, School, SubDepartment
from app.models.permission import TemporaryDelegation, UserPermission

ROLE_PERMISSIONS = {
    "dept_admin": {
        "org:manage",
        "permissions:manage",
        "audit:read",
        "dashboard:view",
        "cohort:view",
        "cohort:grade",
    },
    "faculty_advisor": {"dashboard:view", "cohort:view", "cohort:grade"},
    "corporate_mentor": {"dashboard:view", "cohort:view", "cohort:grade"},
    "student": {"dashboard:view", "assessment:view:self"},
}


def _get_user_school_ids(user) -> set[int]:
    """Return school IDs associated with *user* via their CohortMember rows.

    Legacy fallback for ``scope:dept`` when majors are not yet linked to
    :class:`~app.models.org.SubDepartment` rows.
    """
    cohort_ids = [cm.cohort_id for cm in CohortMember.query.filter_by(user_id=user.id).all()]
    if not cohort_ids:
        return set()
    rows = (
        db.session.query(Major.school_id)
        .join(Class, Class.major_id == Major.id)
        .join(Cohort, Cohort.class_id == Class.id)
        .filter(Cohort.id.in_(cohort_ids))
        .distinct()
        .all()
    )
    return {row[0] for row in rows if row[0]}


def _get_user_department_ids(user) -> set[int]:
    """Department IDs implied by the user's cohort memberships (via major → sub-department)."""
    cohort_ids = [cm.cohort_id for cm in CohortMember.query.filter_by(user_id=user.id).all()]
    if not cohort_ids:
        return set()
    rows = (
        db.session.query(SubDepartment.department_id)
        .join(Major, Major.sub_department_id == SubDepartment.id)
        .join(Class, Class.major_id == Major.id)
        .join(Cohort, Cohort.class_id == Class.id)
        .filter(Cohort.id.in_(cohort_ids), Major.sub_department_id.isnot(None))
        .distinct()
        .all()
    )
    return {row[0] for row in rows if row[0]}


def _json_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, list):
        return [str(x) for x in parsed]
    return []


def get_user_permissions(user, effective_role: str | None = None) -> set[str]:
    """Return the active permission set for *user*.

    When *effective_role* is given (e.g. the current session role after a
    role-switch) the base permissions for that role are used instead of the
    user's stored primary role.  Explicit grants and active delegations are
    always added on top, but only when they are not blocked by the narrower
    effective role.  The narrowing rule: if the effective role is ``student``
    we cap delegation/explicit extras to only those permissions also present
    in the student base set, preventing privilege escalation through grants
    that were issued for the primary role.
    """
    resolved_role = effective_role if effective_role else user.role
    base = set(ROLE_PERMISSIONS.get(resolved_role, set()))
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    explicit = UserPermission.query.filter(UserPermission.user_id == user.id).all()
    for row in explicit:
        if row.expires_at and row.expires_at < now:
            continue
        base.add(row.permission)

    delegations = TemporaryDelegation.query.filter(
        TemporaryDelegation.delegate_id == user.id,
        TemporaryDelegation.is_active.is_(True),
        TemporaryDelegation.expires_at >= now,
    ).all()
    for delegation in delegations:
        for permission in _json_list(delegation.permissions):
            base.add(permission)

    return base


def has_permission(user, permission: str, effective_role: str | None = None) -> bool:
    return permission in get_user_permissions(user, effective_role=effective_role)


def get_delegation_cohort_ids(user) -> set[int] | None:
    """
    Returns the set of cohort IDs accessible via active delegations,
    or None if any active delegation has global scope (no restriction).
    Returns an empty set if the user has no active delegations.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    delegations = TemporaryDelegation.query.filter(
        TemporaryDelegation.delegate_id == user.id,
        TemporaryDelegation.is_active.is_(True),
        TemporaryDelegation.expires_at >= now,
    ).all()

    if not delegations:
        return set()

    cohort_ids: set[int] = set()
    for d in delegations:
        scope = (d.scope or "").strip()
        if not scope or scope == "scope:global":
            return None
        if scope.startswith("scope:cohort:"):
            try:
                cohort_ids.add(int(scope.split(":")[-1]))
            except (ValueError, IndexError):
                pass
    return cohort_ids


def get_accessible_cohorts(user, effective_role: str | None = None) -> list[Cohort]:
    role = effective_role or user.role
    if role == "dept_admin":
        return Cohort.query.filter(Cohort.is_active.is_(True)).all()

    scope_cohort_ids: set[int] = set()
    scopes = {
        up.permission
        for up in UserPermission.query.filter_by(user_id=user.id).all()
        if up.permission.startswith("scope:")
    }
    if "scope:global" in scopes:
        return Cohort.query.filter(Cohort.is_active.is_(True)).all()

    # scope:dept — same department (and all its sub-departments) as the user's cohort memberships.
    if "scope:dept" in scopes:
        user_dept_ids = _get_user_department_ids(user)
        if user_dept_ids:
            ids = (
                db.session.query(Cohort.id)
                .join(Class, Class.id == Cohort.class_id)
                .join(Major, Major.id == Class.major_id)
                .join(SubDepartment, SubDepartment.id == Major.sub_department_id)
                .filter(SubDepartment.department_id.in_(user_dept_ids), Cohort.is_active.is_(True))
                .all()
            )
            scope_cohort_ids.update(row[0] for row in ids)
        else:
            dept_school_ids = _get_user_school_ids(user)
            if dept_school_ids:
                ids = (
                    db.session.query(Cohort.id)
                    .join(Class, Class.id == Cohort.class_id)
                    .join(Major, Major.id == Class.major_id)
                    .filter(Major.school_id.in_(dept_school_ids), Cohort.is_active.is_(True))
                    .all()
                )
                scope_cohort_ids.update(row[0] for row in ids)

    for s in scopes:
        if s.startswith("scope:school:"):
            school_id = int(s.split(":")[-1])
            ids = (
                db.session.query(Cohort.id)
                .join(Class, Class.id == Cohort.class_id)
                .join(Major, Major.id == Class.major_id)
                .filter(Major.school_id == school_id, Cohort.is_active.is_(True))
                .all()
            )
            scope_cohort_ids.update(row[0] for row in ids)

    for s in scopes:
        if s.startswith("scope:major:"):
            major_id = int(s.split(":")[-1])
            ids = (
                db.session.query(Cohort.id)
                .join(Class, Class.id == Cohort.class_id)
                .filter(Class.major_id == major_id, Cohort.is_active.is_(True))
                .all()
            )
            scope_cohort_ids.update(row[0] for row in ids)

    for s in scopes:
        if s.startswith("scope:class:"):
            class_id = int(s.split(":")[-1])
            ids = (
                db.session.query(Cohort.id)
                .filter(Cohort.class_id == class_id, Cohort.is_active.is_(True))
                .all()
            )
            scope_cohort_ids.update(row[0] for row in ids)

    for s in scopes:
        if s.startswith("scope:cohort:"):
            scope_cohort_ids.add(int(s.split(":")[-1]))

    member_ids = {
        a.cohort_id for a in CohortMember.query.filter_by(user_id=user.id).all()
    }
    cohort_ids = scope_cohort_ids | member_ids

    delegation_ids = get_delegation_cohort_ids(user)
    if delegation_ids is not None and len(delegation_ids) > 0:
        directly_accessible = {cm.cohort_id for cm in CohortMember.query.filter_by(user_id=user.id).all()}
        for cid in list(cohort_ids):
            if cid not in directly_accessible and cid not in delegation_ids:
                cohort_ids.discard(cid)

    if not cohort_ids:
        return []
    return Cohort.query.filter(Cohort.id.in_(cohort_ids), Cohort.is_active.is_(True)).all()


def get_accessible_schools(user, effective_role: str | None = None) -> list[School]:
    role = effective_role or user.role
    if role == "dept_admin":
        explicit = [
            up.permission.split(":")[-1]
            for up in UserPermission.query.filter(UserPermission.user_id == user.id).all()
            if up.permission.startswith("scope:school:")
        ]
        if explicit:
            school_ids = [int(x) for x in explicit if str(x).isdigit()]
            return School.query.filter(School.is_active.is_(True), School.id.in_(school_ids)).all()
        return School.query.filter(School.is_active.is_(True)).all()

    cohort_ids = [c.id for c in get_accessible_cohorts(user, effective_role=role)]
    if not cohort_ids:
        return []

    rows = (
        db.session.query(School)
        .join(Major, Major.school_id == School.id)
        .join(Class, Class.major_id == Major.id)
        .join(Cohort, Cohort.class_id == Class.id)
        .filter(Cohort.id.in_(cohort_ids), School.is_active.is_(True))
        .distinct()
        .all()
    )
    return rows


def _scope_permits_cohort(user, cohort_id: int) -> bool:
    """
    Returns True if any explicit scope permission in UserPermission grants
    access to the given cohort via the org hierarchy:
      scope:global
      scope:school:<id>  -> all cohorts in that school
      scope:major:<id>   -> all cohorts in that major
      scope:class:<id>   -> all cohorts in that class
      scope:cohort:<id>  -> that specific cohort
    """
    cohort = db.session.get(Cohort, cohort_id)
    if not cohort:
        return False
    klass = db.session.get(Class, cohort.class_id) if cohort.class_id else None
    major = db.session.get(Major, klass.major_id) if klass and klass.major_id else None
    school = db.session.get(School, major.school_id) if major and major.school_id else None
    scopes_granted = {
        up.permission
        for up in UserPermission.query.filter_by(user_id=user.id).all()
        if up.permission.startswith("scope:")
    }
    if "scope:global" in scopes_granted:
        return True
    # scope:dept — same department tree as cohort memberships, or legacy school match.
    if "scope:dept" in scopes_granted:
        user_dept_ids = _get_user_department_ids(user)
        if major and major.sub_department_id:
            sd = db.session.get(SubDepartment, major.sub_department_id)
            if sd and sd.department_id in user_dept_ids:
                return True
        user_school_ids = _get_user_school_ids(user)
        if school and school.id in user_school_ids:
            return True
    if school and f"scope:school:{school.id}" in scopes_granted:
        return True
    if major and f"scope:major:{major.id}" in scopes_granted:
        return True
    if klass and f"scope:class:{klass.id}" in scopes_granted:
        return True
    if f"scope:cohort:{cohort_id}" in scopes_granted:
        return True
    return False


def can_access_cohort(user, cohort_id: int, effective_role: str | None = None) -> bool:
    role = effective_role or user.role
    if role == "dept_admin":
        return Cohort.query.filter_by(id=cohort_id).first() is not None
    if _scope_permits_cohort(user, cohort_id):
        return True
    if (
        CohortMember.query.filter(
            CohortMember.user_id == user.id,
            CohortMember.cohort_id == cohort_id,
        ).first()
        is not None
    ):
        return True

    delegation_ids = get_delegation_cohort_ids(user)
    if delegation_ids is None:
        return True
    return cohort_id in delegation_ids


def can_access_student(user, student_id: int, effective_role: str | None = None) -> bool:
    role = effective_role or user.role
    if role == "dept_admin":
        return True
    if role == "student":
        return user.id == student_id

    my_cohort_ids = [r.cohort_id for r in CohortMember.query.filter(CohortMember.user_id == user.id).all()]
    if not my_cohort_ids:
        return False
    shared = (
        CohortMember.query.filter(
            CohortMember.user_id == student_id,
            CohortMember.role_in_cohort == "student",
            CohortMember.cohort_id.in_(my_cohort_ids),
        ).first()
        is not None
    )
    return shared


def expire_delegations() -> int:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = TemporaryDelegation.query.filter(
        TemporaryDelegation.is_active.is_(True),
        TemporaryDelegation.expires_at < now,
    ).all()
    for row in rows:
        row.is_active = False
        db.session.add(row)
    db.session.commit()
    return len(rows)


def get_available_roles(user) -> list[str]:
    """Returns the user's primary role plus any extra roles granted via UserPermission."""
    roles = [user.role]
    extra = [
        up.permission[len("role:") :]
        for up in UserPermission.query.filter_by(user_id=user.id).all()
        if up.permission.startswith("role:")
    ]
    for role_name in extra:
        if role_name not in roles:
            roles.append(role_name)
    return roles


def get_nav_for_role(user, active_role: str | None = None):
    if not user:
        return []

    role = active_role or user.role

    nav = {
        "dept_admin": [
            ("Dashboard", "/dashboard"),
            ("Admin", "/admin/dashboard"),
            ("Org Structure", "/admin/org/schools"),
            ("Question Bank", "/admin/questions"),
            ("Papers", "/admin/papers"),
            ("Assignments", "/admin/assignments"),
            ("Users", "/admin/users"),
            ("Reports", "/reports"),
            ("Permissions", "/admin/permissions/templates"),
            ("Audit Logs", "/admin/audit-logs"),
        ],
        "faculty_advisor": [
            ("Dashboard", "/dashboard"),
            ("My Cohorts", "/cohorts"),
            ("Grading", "/grading"),
            ("Assignment Grading", "/assignments/grading"),
            ("Reports", "/reports"),
        ],
        "corporate_mentor": [
            ("Dashboard", "/dashboard"),
            ("My Cohorts", "/cohorts"),
            ("Grading", "/grading"),
            ("Assignment Grading", "/assignments/grading"),
            ("Reports", "/reports"),
        ],
        "student": [
            ("Dashboard", "/dashboard"),
            ("My Assessments", "/quiz"),
            ("Assignments", "/assignments"),
        ],
    }
    items = nav.get(role, [])
    items = list(items) + [("Switch Role", "/switch-role")]
    return [{"label": label, "href": href} for label, href in items]
