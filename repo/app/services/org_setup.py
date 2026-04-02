"""Ensure department / sub-department hierarchy exists and majors are linked."""

from sqlalchemy import inspect, text

from app.extensions import db
from app.models.org import Department, Major, School, SubDepartment


def get_or_create_default_subdepartment(school_id: int) -> SubDepartment:
    """Return the default sub-department for a school (creates Department + SubDepartment if needed)."""
    school = db.session.get(School, school_id)
    if not school:
        raise ValueError("school not found")

    dept = Department.query.filter_by(school_id=school_id).first()
    if not dept:
        code = (school.code or "SCH") + "-DEPT"
        dept = Department(school_id=school_id, name=f"{school.name} — Department", code=code[:32])
        db.session.add(dept)
        db.session.flush()

    sub = SubDepartment.query.filter_by(department_id=dept.id).first()
    if not sub:
        sub = SubDepartment(department_id=dept.id, name="General", code="GEN")
        db.session.add(sub)
        db.session.flush()

    return sub


def ensure_department_hierarchy() -> None:
    """Create tables/columns if missing, seed default Department/SubDepartment per school, backfill majors."""
    insp = inspect(db.engine)
    tables = insp.get_table_names()

    if "departments" not in tables or "sub_departments" not in tables:
        return

    if "majors" in tables:
        cols = {c["name"] for c in insp.get_columns("majors")}
        if "sub_department_id" not in cols:
            db.session.execute(text("ALTER TABLE majors ADD COLUMN sub_department_id INTEGER"))
            db.session.commit()

    for school in School.query.all():
        sub = get_or_create_default_subdepartment(school.id)
        Major.query.filter(Major.school_id == school.id, Major.sub_department_id.is_(None)).update(
            {"sub_department_id": sub.id},
            synchronize_session=False,
        )
    db.session.commit()
