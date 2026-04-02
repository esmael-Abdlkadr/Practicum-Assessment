from datetime import datetime

from flask import Blueprint, abort, render_template, request

from app.extensions import db
from app.models.assignment import CohortMember
from app.models.org import Class, Cohort, Major, School, SubDepartment
from app.models.user import User
from app.services import audit_service
from app.services.org_setup import get_or_create_default_subdepartment
from app.services.decorators import login_required, require_role

org_bp = Blueprint("org", __name__, url_prefix="/admin/org")


def _org_context():
    return {
        "schools": School.query.order_by(School.id.desc()).all(),
        "majors": Major.query.order_by(Major.id.desc()).all(),
        "sub_departments": SubDepartment.query.order_by(SubDepartment.id.desc()).all(),
        "classes": Class.query.order_by(Class.id.desc()).all(),
        "cohorts": Cohort.query.order_by(Cohort.id.desc()).all(),
    }


@org_bp.get("/schools")
@login_required
@require_role("dept_admin")
def schools_page():
    return render_template("admin/org/schools.html", **_org_context())


@org_bp.post("/schools")
@login_required
@require_role("dept_admin")
def create_school():
    school = School(
        name=(request.form.get("name") or "").strip(),
        code=(request.form.get("code") or "").strip() or None,
    )
    if not school.name:
        return abort(400)
    db.session.add(school)
    db.session.commit()
    get_or_create_default_subdepartment(school.id)
    db.session.commit()
    audit_service.log(action="ORG_SCHOOL_CREATED", resource_type="school", resource_id=school.id, new_value={"name": school.name})
    return render_template("admin/org/_schools_list.html", schools=School.query.order_by(School.id.desc()).all())


@org_bp.put("/schools/<int:id>")
@login_required
@require_role("dept_admin")
def update_school(id: int):
    school = School.query.get_or_404(id)
    old = {"name": school.name, "code": school.code, "is_active": school.is_active}
    school.name = (request.form.get("name") or school.name).strip()
    school.code = (request.form.get("code") or school.code)
    db.session.add(school)
    db.session.commit()
    audit_service.log(action="ORG_SCHOOL_UPDATED", resource_type="school", resource_id=school.id, old_value=old, new_value={"name": school.name, "code": school.code})
    return render_template("admin/org/_schools_list.html", schools=School.query.order_by(School.id.desc()).all())


@org_bp.delete("/schools/<int:id>")
@login_required
@require_role("dept_admin")
def delete_school(id: int):
    school = School.query.get_or_404(id)
    school.is_active = False
    db.session.add(school)
    db.session.commit()
    audit_service.log(action="ORG_SCHOOL_DELETED", resource_type="school", resource_id=school.id)
    return render_template("admin/org/_schools_list.html", schools=School.query.order_by(School.id.desc()).all())


@org_bp.post("/majors")
@login_required
@require_role("dept_admin")
def create_major():
    name = (request.form.get("name") or "").strip()
    if not name:
        return "<div class='alert alert-danger' role='alert'>Major name is required.</div>", 400
    school_id = int(request.form.get("school_id"))
    sub_raw = (request.form.get("sub_department_id") or "").strip()
    sub_department_id = int(sub_raw) if sub_raw.isdigit() else get_or_create_default_subdepartment(school_id).id
    major = Major(
        school_id=school_id,
        sub_department_id=sub_department_id,
        name=name,
        code=(request.form.get("code") or "").strip() or None,
    )
    db.session.add(major)
    db.session.commit()
    audit_service.log(action="ORG_MAJOR_CREATED", resource_type="major", resource_id=major.id)
    return render_template("admin/org/_majors_list.html", majors=Major.query.order_by(Major.id.desc()).all())


@org_bp.put("/majors/<int:id>")
@login_required
@require_role("dept_admin")
def update_major(id: int):
    major = Major.query.get_or_404(id)
    major.name = (request.form.get("name") or major.name).strip()
    major.code = (request.form.get("code") or major.code)
    db.session.add(major)
    db.session.commit()
    audit_service.log(action="ORG_MAJOR_UPDATED", resource_type="major", resource_id=major.id)
    return render_template("admin/org/_majors_list.html", majors=Major.query.order_by(Major.id.desc()).all())


@org_bp.delete("/majors/<int:id>")
@login_required
@require_role("dept_admin")
def delete_major(id: int):
    major = Major.query.get_or_404(id)
    db.session.delete(major)
    db.session.commit()
    audit_service.log(action="ORG_MAJOR_DELETED", resource_type="major", resource_id=id)
    return render_template("admin/org/_majors_list.html", majors=Major.query.order_by(Major.id.desc()).all())


@org_bp.post("/classes")
@login_required
@require_role("dept_admin")
def create_class():
    name = (request.form.get("name") or "").strip()
    if not name:
        return "<div class='alert alert-danger' role='alert'>Class name is required.</div>", 400
    try:
        year = int(request.form.get("year") or 0) if request.form.get("year") else None
    except (ValueError, TypeError):
        return "<div class='alert alert-danger' role='alert'>Invalid year value.</div>", 400

    classroom = Class(
        major_id=int(request.form.get("major_id")),
        name=name,
        year=year,
    )
    db.session.add(classroom)
    db.session.commit()
    audit_service.log(action="ORG_CLASS_CREATED", resource_type="class", resource_id=classroom.id)
    return render_template("admin/org/_classes_list.html", classes=Class.query.order_by(Class.id.desc()).all())


@org_bp.put("/classes/<int:id>")
@login_required
@require_role("dept_admin")
def update_class(id: int):
    classroom = Class.query.get_or_404(id)
    classroom.name = (request.form.get("name") or classroom.name).strip()
    if request.form.get("year"):
        try:
            classroom.year = int(request.form.get("year") or 0)
        except (ValueError, TypeError):
            return "<div class='alert alert-danger' role='alert'>Invalid year value.</div>", 400
    db.session.add(classroom)
    db.session.commit()
    audit_service.log(action="ORG_CLASS_UPDATED", resource_type="class", resource_id=classroom.id)
    return render_template("admin/org/_classes_list.html", classes=Class.query.order_by(Class.id.desc()).all())


@org_bp.delete("/classes/<int:id>")
@login_required
@require_role("dept_admin")
def delete_class(id: int):
    classroom = Class.query.get_or_404(id)
    db.session.delete(classroom)
    db.session.commit()
    audit_service.log(action="ORG_CLASS_DELETED", resource_type="class", resource_id=id)
    return render_template("admin/org/_classes_list.html", classes=Class.query.order_by(Class.id.desc()).all())


@org_bp.post("/cohorts")
@login_required
@require_role("dept_admin")
def create_cohort():
    def _parse_date(raw):
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw).date()
        except (ValueError, TypeError):
            return None

    start_raw = request.form.get("start_date", "")
    end_raw = request.form.get("end_date", "")
    try:
        start_date = datetime.fromisoformat(start_raw).date() if start_raw else None
        end_date = datetime.fromisoformat(end_raw).date() if end_raw else None
    except (ValueError, TypeError):
        return "<div class='alert alert-danger' role='alert'>Invalid date format.</div>", 400

    cohort_name = (request.form.get("name") or "").strip()
    if not cohort_name:
        return "<div class='alert alert-danger' role='alert'>Cohort name is required.</div>", 400

    cohort = Cohort(
        class_id=int(request.form.get("class_id")),
        name=cohort_name,
        internship_term=(request.form.get("internship_term") or "").strip() or None,
        start_date=start_date,
        end_date=end_date,
        is_active=True,
    )
    db.session.add(cohort)
    db.session.commit()
    audit_service.log(action="ORG_COHORT_CREATED", resource_type="cohort", resource_id=cohort.id)
    return render_template("admin/org/_cohorts_list.html", cohorts=Cohort.query.order_by(Cohort.id.desc()).all())


@org_bp.put("/cohorts/<int:id>")
@login_required
@require_role("dept_admin")
def update_cohort(id: int):
    cohort = Cohort.query.get_or_404(id)
    cohort.name = (request.form.get("name") or cohort.name).strip()
    cohort.internship_term = (request.form.get("internship_term") or cohort.internship_term)
    db.session.add(cohort)
    db.session.commit()
    audit_service.log(action="ORG_COHORT_UPDATED", resource_type="cohort", resource_id=cohort.id)
    return render_template("admin/org/_cohorts_list.html", cohorts=Cohort.query.order_by(Cohort.id.desc()).all())


@org_bp.delete("/cohorts/<int:id>")
@login_required
@require_role("dept_admin")
def delete_cohort(id: int):
    cohort = Cohort.query.get_or_404(id)
    cohort.is_active = False
    db.session.add(cohort)
    db.session.commit()
    audit_service.log(action="ORG_COHORT_DELETED", resource_type="cohort", resource_id=id)
    return render_template("admin/org/_cohorts_list.html", cohorts=Cohort.query.order_by(Cohort.id.desc()).all())


@org_bp.get("/cohorts/<int:id>/members")
@login_required
@require_role("dept_admin")
def cohort_members(id: int):
    cohort = Cohort.query.get_or_404(id)
    members = (
        db.session.query(CohortMember, User)
        .join(User, User.id == CohortMember.user_id)
        .filter(CohortMember.cohort_id == id)
        .all()
    )
    users = User.query.order_by(User.username.asc()).all()
    return render_template("admin/org/cohort_members.html", cohort=cohort, members=members, users=users)


@org_bp.post("/cohorts/<int:id>/members")
@login_required
@require_role("dept_admin")
def add_cohort_member(id: int):
    user_id = int(request.form.get("user_id"))
    role_in_cohort = (request.form.get("role_in_cohort") or "").strip()
    if role_in_cohort not in {"student", "faculty_advisor", "corporate_mentor"}:
        return abort(400)

    existing = CohortMember.query.filter_by(cohort_id=id, user_id=user_id).first()
    if not existing:
        row = CohortMember(cohort_id=id, user_id=user_id, role_in_cohort=role_in_cohort)
        db.session.add(row)
        db.session.commit()
        audit_service.log(action="ORG_COHORT_MEMBER_ADDED", resource_type="cohort", resource_id=id, extra={"user_id": user_id, "role_in_cohort": role_in_cohort})

    members = (
        db.session.query(CohortMember, User)
        .join(User, User.id == CohortMember.user_id)
        .filter(CohortMember.cohort_id == id)
        .all()
    )
    return render_template("admin/org/_members_table.html", members=members, cohort_id=id)


@org_bp.delete("/cohorts/<int:id>/members/<int:user_id>")
@login_required
@require_role("dept_admin")
def remove_cohort_member(id: int, user_id: int):
    row = CohortMember.query.filter_by(cohort_id=id, user_id=user_id).first()
    if row:
        db.session.delete(row)
        db.session.commit()
        audit_service.log(action="ORG_COHORT_MEMBER_REMOVED", resource_type="cohort", resource_id=id, extra={"user_id": user_id})

    members = (
        db.session.query(CohortMember, User)
        .join(User, User.id == CohortMember.user_id)
        .filter(CohortMember.cohort_id == id)
        .all()
    )
    return render_template("admin/org/_members_table.html", members=members, cohort_id=id)
