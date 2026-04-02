from app.extensions import db
from app.models.base import BaseModel, _utcnow


class AnomalyFlag(BaseModel):
    __tablename__ = "anomaly_flags"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    username = db.Column(db.String(64), nullable=False)
    anomaly_type = db.Column(db.String(128), nullable=False)
    detected_at = db.Column(db.DateTime, default=_utcnow)
    reviewed = db.Column(db.Boolean, default=False)
