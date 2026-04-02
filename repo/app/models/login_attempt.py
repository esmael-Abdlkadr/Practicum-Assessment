from app.extensions import db
from app.models.base import BaseModel, _utcnow


class LoginAttempt(BaseModel):
    __tablename__ = "login_attempts"

    username = db.Column(db.String(64), nullable=False)
    ip_address = db.Column(db.String(64))
    success = db.Column(db.Boolean, default=False)
    attempted_at = db.Column(db.DateTime, default=_utcnow)
