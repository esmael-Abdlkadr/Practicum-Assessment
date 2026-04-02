import json

from sqlalchemy import event

from app.extensions import db
from app.models.base import BaseModel


class AuditLog(BaseModel):
    __tablename__ = "audit_logs"

    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    actor_username = db.Column(db.String(64))
    action = db.Column(db.String(128), nullable=False)
    resource_type = db.Column(db.String(64))
    resource_id = db.Column(db.String(64))
    old_value = db.Column(db.Text)
    new_value = db.Column(db.Text)
    ip_address = db.Column(db.String(64))
    device_fingerprint = db.Column(db.String(256))
    extra = db.Column(db.Text)
    updated_at = None

    def update(self, **_kwargs):
        raise PermissionError("Audit logs are immutable")

    def delete(self):
        raise PermissionError("Audit logs are immutable")

    @staticmethod
    def to_json(value):
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return json.dumps(value, default=str)


@event.listens_for(AuditLog, "before_update", propagate=True)
def _prevent_update(_mapper, _connection, _target):
    raise PermissionError("Audit logs are immutable")


@event.listens_for(AuditLog, "before_delete", propagate=True)
def _prevent_delete(_mapper, _connection, _target):
    raise PermissionError("Audit logs are immutable")
