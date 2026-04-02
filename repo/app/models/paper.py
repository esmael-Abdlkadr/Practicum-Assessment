from app.extensions import db
from app.models.base import BaseModel


class Paper(BaseModel):
    __tablename__ = "papers"

    title = db.Column(db.String(256), nullable=False)
    description = db.Column(db.Text)
    cohort_id = db.Column(db.Integer, db.ForeignKey("cohorts.id"))
    creator_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    status = db.Column(db.String(32), default="draft")
    time_limit_min = db.Column(db.Integer, default=45)
    max_attempts = db.Column(db.Integer, default=1)
    available_from = db.Column(db.DateTime, nullable=True)
    available_until = db.Column(db.DateTime, nullable=True)
    randomize = db.Column(db.Boolean, default=False)
    draw_count = db.Column(db.Integer, nullable=True)
    draw_tags = db.Column(db.Text, nullable=True)
    shuffle_options = db.Column(db.Boolean, default=True)
    total_score = db.Column(db.Float, default=100.0)
    published_at = db.Column(db.DateTime, nullable=True)


class PaperQuestion(BaseModel):
    __tablename__ = "paper_questions"

    paper_id = db.Column(db.Integer, db.ForeignKey("papers.id"))
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"))
    order_index = db.Column(db.Integer, default=0)
    score_points = db.Column(db.Float)

    __table_args__ = (db.UniqueConstraint("paper_id", "question_id"),)
