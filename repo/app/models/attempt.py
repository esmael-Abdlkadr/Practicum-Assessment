from app.extensions import db
from app.models.base import BaseModel, _utcnow


class Attempt(BaseModel):
    __tablename__ = "attempts"

    paper_id = db.Column(db.Integer, db.ForeignKey("papers.id"))
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    status = db.Column(db.String(32), default="in_progress")
    started_at = db.Column(db.DateTime, default=_utcnow)
    submitted_at = db.Column(db.DateTime, nullable=True)
    finalized_at = db.Column(db.DateTime, nullable=True)
    time_limit_min = db.Column(db.Integer)
    expires_at = db.Column(db.DateTime)
    score = db.Column(db.Float, nullable=True)
    autosave_count = db.Column(db.Integer, default=0)
    submission_token = db.Column(db.String(64), unique=True)


class AttemptAnswer(BaseModel):
    __tablename__ = "attempt_answers"

    attempt_id = db.Column(db.Integer, db.ForeignKey("attempts.id"))
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"))
    answer = db.Column(db.Text)
    saved_at = db.Column(db.DateTime, default=_utcnow)
    is_autosave = db.Column(db.Boolean, default=False)

    __table_args__ = (db.UniqueConstraint("attempt_id", "question_id"),)
