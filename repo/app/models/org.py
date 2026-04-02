from app.extensions import db
from app.models.base import BaseModel


class School(BaseModel):
    __tablename__ = "schools"

    name = db.Column(db.String(128), nullable=False)
    code = db.Column(db.String(32), unique=True)
    is_active = db.Column(db.Boolean, default=True)


class Department(BaseModel):
    """Top-level academic unit under a school (maps to prompt “department”)."""

    __tablename__ = "departments"

    school_id = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False)
    name = db.Column(db.String(128), nullable=False)
    code = db.Column(db.String(32))


class SubDepartment(BaseModel):
    """Sub-unit under a department (maps to prompt “sub-department”)."""

    __tablename__ = "sub_departments"

    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=False)
    name = db.Column(db.String(128), nullable=False)
    code = db.Column(db.String(32))


class Major(BaseModel):
    __tablename__ = "majors"

    school_id = db.Column(db.Integer, db.ForeignKey("schools.id"))
    sub_department_id = db.Column(db.Integer, db.ForeignKey("sub_departments.id"), nullable=True)
    name = db.Column(db.String(128), nullable=False)
    code = db.Column(db.String(32))


class Class(BaseModel):
    __tablename__ = "classes"

    major_id = db.Column(db.Integer, db.ForeignKey("majors.id"))
    name = db.Column(db.String(128), nullable=False)
    year = db.Column(db.Integer)


class Cohort(BaseModel):
    __tablename__ = "cohorts"

    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"))
    name = db.Column(db.String(128), nullable=False)
    internship_term = db.Column(db.String(64))
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    is_active = db.Column(db.Boolean, default=True)
