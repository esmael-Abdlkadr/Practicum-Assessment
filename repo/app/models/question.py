from datetime import datetime, timezone

from app.extensions import db
from app.models.base import BaseModel


class Question(BaseModel):
    __tablename__ = "questions"

    creator_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    school_id = db.Column(db.Integer, db.ForeignKey("schools.id"))
    question_type = db.Column(db.String(32), nullable=False)
    stem = db.Column(db.Text, nullable=False)
    options = db.Column(db.Text)
    correct_answer = db.Column(db.Text)
    explanation = db.Column(db.Text)
    tags = db.Column(db.Text)
    difficulty = db.Column(db.String(16), default="medium")
    score_points = db.Column(db.Float, default=1.0)
    is_active = db.Column(db.Boolean, default=True)
    deleted_at = db.Column(db.DateTime, nullable=True)

    def soft_delete(self):
        self.is_active = False
        self.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)
