from app.extensions import db
from app.models.base import BaseModel


class PermissionTemplate(BaseModel):
    __tablename__ = "permission_templates"

    name = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(32))
    permissions = db.Column(db.Text)


class UserPermission(BaseModel):
    __tablename__ = "user_permissions"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    permission = db.Column(db.String(128), nullable=False)
    granted_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    expires_at = db.Column(db.DateTime, nullable=True)


class TemporaryDelegation(BaseModel):
    __tablename__ = "temporary_delegations"

    delegator_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    delegate_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    scope = db.Column(db.String(256))
    permissions = db.Column(db.Text)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
