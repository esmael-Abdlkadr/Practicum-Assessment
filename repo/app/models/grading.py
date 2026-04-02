from app.extensions import db
from app.models.base import BaseModel


class GradingResult(BaseModel):
    __tablename__ = "grading_results"

    attempt_id = db.Column(db.Integer, db.ForeignKey("attempts.id"))
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"))
    score_awarded = db.Column(db.Float, default=0.0)
    max_score = db.Column(db.Float)
    is_correct = db.Column(db.Boolean, nullable=True)
    graded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    graded_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(32), default="pending")


class GradingComment(BaseModel):
    __tablename__ = "grading_comments"

    attempt_id = db.Column(db.Integer, db.ForeignKey("attempts.id"))
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"))
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    comment_text = db.Column(db.Text, nullable=False)
    is_internal = db.Column(db.Boolean, default=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("grading_comments.id"), nullable=True)
    replies = db.relationship(
        "GradingComment",
        backref=db.backref("parent", remote_side="GradingComment.id"),
        lazy="dynamic",
        foreign_keys="[GradingComment.parent_id]",
    )


class Rubric(BaseModel):
    __tablename__ = "rubrics"

    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"))
    criteria = db.Column(db.Text, nullable=False)
