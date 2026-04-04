import json
import re
from datetime import datetime, timedelta, timezone

from flask import Blueprint, abort, redirect, render_template, request, session, url_for

from app.extensions import db
from app.models.permission import PermissionTemplate, TemporaryDelegation, UserPermission
from app.models.user import User
from app.services import audit_service
from app.services.decorators import high_risk_action, login_required, require_role

permissions_bp = Blueprint("permissions", __name__, url_prefix="/admin/permissions")

_CANONICAL_SCOPE_RE = re.compile(r"^scope:(global|dept|school:\d+|major:\d+|class:\d+|cohort:\d+)$")


def _normalize_scope(raw: str) -> tuple[str, str | None]:
    """Normalize raw scope input to canonical ``scope:<type>[:<id>]`` format.

    Accepts both canonical (``scope:cohort:42``) and shorthand (``cohort:42``)
    forms.  Returns ``(canonical_scope, error_or_None)``.
    """
    s = (raw or "").strip()
    if not s:
        return s, None  # empty = no restriction (global delegation)
    if _CANONICAL_SCOPE_RE.match(s):
        return s, None
    # Try normalizing shorthand: cohort:42 -> scope:cohort:42
    normalized = f"scope:{s}"
    if _CANONICAL_SCOPE_RE.match(normalized):
        return normalized, None
    return s, (
        f"Invalid scope format '{s}'. "
        "Use canonical format: scope:cohort:<id>, scope:school:<id>, "
        "scope:global — or shorthand: cohort:<id>, school:<id>, global."
    )


@permissions_bp.get("/templates")
@login_required
@require_role("dept_admin")
def templates_page():
    templates = PermissionTemplate.query.order_by(PermissionTemplate.id.desc()).all()
    users = User.query.order_by(User.username.asc()).all()
    return render_template("admin/permissions/templates.html", templates=templates, users=users)


@permissions_bp.post("/templates")
@login_required
@require_role("dept_admin")
@high_risk_action
def create_template():
    name = (request.form.get("name") or "").strip()
    role = (request.form.get("role") or "").strip() or None
    permissions_raw = (request.form.get("permissions") or "").strip()
    permissions = [p.strip() for p in permissions_raw.split(",") if p.strip()]
    if not name:
        return "<div class='alert alert-danger' role='alert'>Invalid request.</div>", 400

    template = PermissionTemplate(name=name, role=role, permissions=json.dumps(permissions))
    db.session.add(template)
    db.session.commit()
    audit_service.log(action="PERMISSION_TEMPLATE_CREATED", resource_type="permission_template", resource_id=template.id)
    return redirect(url_for("permissions.templates_page"))


@permissions_bp.post("/grant")
@login_required
@require_role("dept_admin")
@high_risk_action
def grant_user_permission_form():
    """Flat grant endpoint — user_id submitted as form data, no JS URL rewriting needed."""
    user_id_raw = request.form.get("user_id")
    if not user_id_raw or not str(user_id_raw).isdigit():
        return "<div class='alert alert-danger'>Invalid user selection.</div>", 400
    return _do_grant_permission(int(user_id_raw))


@permissions_bp.post("/users/<int:user_id>/grant")
@login_required
@require_role("dept_admin")
@high_risk_action
def grant_user_permission(user_id: int):
    return _do_grant_permission(user_id)


def _do_grant_permission(user_id: int):
    template_id = request.form.get("template_id")
    custom_permission = (request.form.get("permission") or "").strip()
    expires_at_raw = (request.form.get("expires_at") or "").strip()

    if expires_at_raw:
        try:
            expires_at = datetime.fromisoformat(expires_at_raw)
        except (ValueError, TypeError):
            return "<div class='alert alert-danger'>Invalid 'Expires At' date.</div>", 400
    else:
        expires_at = None

    permissions = []
    if template_id:
        template = PermissionTemplate.query.get_or_404(int(template_id))
        permissions.extend(json.loads(template.permissions or "[]"))
    if custom_permission:
        permissions.append(custom_permission)

    actor_id = session.get("user_id")

    for permission in permissions:
        row = UserPermission(user_id=user_id, permission=permission, granted_by=actor_id, expires_at=expires_at)
        db.session.add(row)

    db.session.commit()
    audit_service.log(action="USER_PERMISSION_GRANTED", resource_type="user", resource_id=user_id, extra={"permissions": permissions})
    return redirect(url_for("permissions.templates_page"))


@permissions_bp.get("/delegations")
@login_required
@require_role("dept_admin")
def delegations_page():
    delegations = TemporaryDelegation.query.order_by(TemporaryDelegation.id.desc()).all()
    users = User.query.order_by(User.username.asc()).all()
    return render_template("admin/permissions/delegations.html", delegations=delegations, users=users)


@permissions_bp.post("/delegations")
@login_required
@require_role("dept_admin")
@high_risk_action
def create_delegation():
    delegator_id = int(request.form.get("delegator_id"))
    delegate_id = int(request.form.get("delegate_id"))
    scope, scope_error = _normalize_scope(request.form.get("scope") or "")
    if scope_error:
        return f"<div class='alert alert-danger' role='alert'>{scope_error}</div>", 400
    permissions_raw = (request.form.get("permissions") or "").strip()
    permissions = [p.strip() for p in permissions_raw.split(",") if p.strip()]

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    expires_in_days = int(request.form.get("expires_in_days") or 7)
    if expires_in_days > 30:
        return "<div class='alert alert-danger'>Maximum delegation duration is 30 days.</div>", 400
    expires_at = now + timedelta(days=expires_in_days)

    delegation = TemporaryDelegation(
        delegator_id=delegator_id,
        delegate_id=delegate_id,
        scope=scope,
        permissions=json.dumps(permissions),
        expires_at=expires_at,
        is_active=True,
    )
    db.session.add(delegation)
    db.session.commit()
    audit_service.log(action="TEMP_DELEGATION_CREATED", resource_type="delegation", resource_id=delegation.id)
    if request.headers.get("HX-Request") == "true":
        return "<div class='alert alert-success' role='alert'>Delegation created.</div>"
    return redirect(url_for("permissions.delegations_page"))


@permissions_bp.delete("/delegations/<int:id>")
@login_required
@require_role("dept_admin")
@high_risk_action
def revoke_delegation(id: int):
    delegation = TemporaryDelegation.query.get_or_404(id)
    delegation.is_active = False
    db.session.add(delegation)
    db.session.commit()
    audit_service.log(action="TEMP_DELEGATION_REVOKED", resource_type="delegation", resource_id=id)
    return "<div class='alert alert-success' role='alert'>Delegation revoked.</div>"
