from app.extensions import db
from app.models.base import BaseModel


class CohortMember(BaseModel):
    __tablename__ = "cohort_members"

    cohort_id = db.Column(db.Integer, db.ForeignKey("cohorts.id"))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    role_in_cohort = db.Column(db.String(32))

    __table_args__ = (db.UniqueConstraint("cohort_id", "user_id"),)


class Assignment(BaseModel):
    __tablename__ = "assignments"

    title = db.Column(db.String(256), nullable=False)
    description = db.Column(db.Text)
    cohort_id = db.Column(db.Integer, db.ForeignKey("cohorts.id"), nullable=False)
    creator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    status = db.Column(db.String(32), default="draft")
    due_date = db.Column(db.DateTime, nullable=True)
    max_score = db.Column(db.Float, default=100.0)


class AssignmentSubmission(BaseModel):
    __tablename__ = "assignment_submissions"

    assignment_id = db.Column(db.Integer, db.ForeignKey("assignments.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    content = db.Column(db.Text)
    submitted_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(32), default="draft")

    __table_args__ = (db.UniqueConstraint("assignment_id", "student_id"),)


class AssignmentGrade(BaseModel):
    __tablename__ = "assignment_grades"

    submission_id = db.Column(db.Integer, db.ForeignKey("assignment_submissions.id"), nullable=False, unique=True)
    grader_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    score = db.Column(db.Float, nullable=True)
    feedback = db.Column(db.Text)
    graded_at = db.Column(db.DateTime, nullable=True)
