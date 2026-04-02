import secrets
import string

from flask import Blueprint, abort, render_template, request

from app.extensions import db
from app.models.user import User
from app.services import audit_service, encryption_service
from app.services.auth_service import hash_password, validate_password_strength
from app.services.decorators import high_risk_action, login_required, require_role
from app.services.session_service import get_current_user

admin_users_bp = Blueprint("admin_users", __name__, url_prefix="/admin/users")
_pending_credentials: dict[int, str] = {}


def _temp_password(length: int = 14):
    chars = string.ascii_letters + string.digits + "@#$!"
    while True:
        pwd = "".join(secrets.choice(chars) for _ in range(length))
        ok, _ = validate_password_strength(pwd)
        if ok:
            return pwd


def _query_users():
    search = (request.args.get("search") or "").strip()
    role = (request.args.get("role") or "").strip()
    active = (request.args.get("active") or "").strip()
    query = User.query
    if search:
        query = query.filter((User.username.ilike(f"%{search}%")) | (User.full_name.ilike(f"%{search}%")))
    if role:
        query = query.filter(User.role == role)
    if active == "active":
        query = query.filter(User.is_active.is_(True))
    elif active == "inactive":
        query = query.filter(User.is_active.is_(False))
    return query.order_by(User.id.desc()).all()


@admin_users_bp.get("")
@login_required
@require_role("dept_admin")
def list_users():
    rows = _query_users()
    if request.headers.get("HX-Request") == "true":
        return render_template("admin/users/_rows.html", users=rows)
    return render_template("admin/users/list.html", users=rows)


@admin_users_bp.post("")
@login_required
@require_role("dept_admin")
def create_user():
    actor = get_current_user()
    username = (request.form.get("username") or "").strip()
    if not username:
        return abort(400)
    if User.query.filter_by(username=username).first():
        return "<div class='alert alert-danger' role='alert'>Username already exists.</div>", 400

    role = (request.form.get("role") or "student").strip()
    password = (request.form.get("password") or "").strip()
    generated_password = None
    if not password:
        generated_password = _temp_password()
        password = generated_password

    ok, error = validate_password_strength(password)
    if not ok:
        return f"<div class='alert alert-danger' role='alert'>{error}</div>", 422

    student_id = (request.form.get("student_id") or "").strip()
    student_id_enc = encryption_service.encrypt(student_id) if student_id else None

    user = User(
        username=username,
        full_name=(request.form.get("full_name") or "").strip() or None,
        email=(request.form.get("email") or "").strip() or None,
        role=role,
        password_hash=hash_password(password),
        student_id_enc=student_id_enc,
        is_active=True,
        force_password_change=bool(generated_password),
    )
    db.session.add(user)
    db.session.commit()
    audit_service.log(action="USER_CREATED", resource_type="user", resource_id=user.id)

    rows = _query_users()
    if generated_password:
        _pending_credentials[user.id] = generated_password
        msg = (
            "<div class='alert alert-success' role='alert'>"
            "User created. "
            "<button class='btn btn-sm btn-warning ms-2' "
            f"hx-get='/admin/users/{user.id}/reveal-temp-credential' "
            "hx-target='#temp-cred-area' hx-swap='innerHTML'>"
            "Reveal one-time password</button>"
            "<div id='temp-cred-area'></div>"
            "</div>"
        )
    else:
        msg = ""
    return msg + render_template("admin/users/_rows.html", users=rows)


@admin_users_bp.get("/<int:id>/edit")
@login_required
@require_role("dept_admin")
def edit_form(id: int):
    user = User.query.get_or_404(id)
    return render_template("admin/users/_form.html", user=user)


@admin_users_bp.put("/<int:id>")
@login_required
@require_role("dept_admin")
@high_risk_action
def update_user(id: int):
    user = User.query.get_or_404(id)
    old = {"full_name": user.full_name, "email": user.email, "role": user.role}
    user.full_name = (request.form.get("full_name") or user.full_name or "").strip() or None
    user.email = (request.form.get("email") or user.email or "").strip() or None
    new_role = (request.form.get("role") or user.role).strip()
    user.role = new_role
    student_id = (request.form.get("student_id") or "").strip()
    if student_id:
        user.student_id_enc = encryption_service.encrypt(student_id)
    db.session.add(user)
    db.session.commit()
    audit_service.log(action="USER_UPDATED", resource_type="user", resource_id=user.id, old_value=old, new_value={"full_name": user.full_name, "email": user.email, "role": user.role})
    rows = _query_users()
    return render_template("admin/users/_rows.html", users=rows)


@admin_users_bp.post("/<int:id>/deactivate")
@login_required
@require_role("dept_admin")
def deactivate(id: int):
    user = User.query.get_or_404(id)
    user.is_active = False
    db.session.add(user)
    db.session.commit()
    audit_service.log(action="USER_DEACTIVATED", resource_type="user", resource_id=id)
    return render_template("admin/users/_row.html", user=user)


@admin_users_bp.post("/<int:id>/activate")
@login_required
@require_role("dept_admin")
def activate(id: int):
    user = User.query.get_or_404(id)
    user.is_active = True
    db.session.add(user)
    db.session.commit()
    audit_service.log(action="USER_ACTIVATED", resource_type="user", resource_id=id)
    return render_template("admin/users/_row.html", user=user)


@admin_users_bp.post("/<int:id>/reset-password")
@login_required
@require_role("dept_admin")
@high_risk_action
def reset_password(id: int):
    user = User.query.get_or_404(id)
    temp = _temp_password()
    user.password_hash = hash_password(temp)
    user.force_password_change = True
    db.session.add(user)
    db.session.commit()
    audit_service.log(action="PASSWORD_RESET_BY_ADMIN", resource_type="user", resource_id=id)
    _pending_credentials[user.id] = temp
    return (
        "<div class='alert alert-success' role='alert'>"
        "Password reset. "
        "<button class='btn btn-sm btn-warning ms-2' "
        f"hx-get='/admin/users/{id}/reveal-temp-credential' "
        "hx-target='#temp-cred-area' hx-swap='innerHTML'>"
        "Reveal one-time password</button>"
        "<div id='temp-cred-area'></div>"
        "</div>"
    )


@admin_users_bp.post("/<int:id>/unlock")
@login_required
@require_role("dept_admin")
def unlock(id: int):
    user = User.query.get_or_404(id)
    user.failed_attempts = 0
    user.locked_until = None
    db.session.add(user)
    db.session.commit()
    audit_service.log(action="ACCOUNT_UNLOCKED", resource_type="user", resource_id=id)
    return render_template("admin/users/_row.html", user=user)


@admin_users_bp.get("/<int:id>/reveal-student-id")
@login_required
@require_role("dept_admin")
@high_risk_action
def reveal_student_id(id: int):
    user = User.query.get_or_404(id)
    if not user.student_id_enc:
        return "<span>-</span>"
    plain = encryption_service.decrypt(user.student_id_enc)
    audit_service.log(action="STUDENT_ID_REVEALED", resource_type="user", resource_id=id)
    return f"<span>{plain}</span>"


@admin_users_bp.get("/<int:id>/reveal-temp-credential")
@login_required
@require_role("dept_admin")
@high_risk_action
def reveal_temp_credential(id: int):
    cred = _pending_credentials.pop(id, None)
    if cred is None:
        return "<div class='alert alert-warning'>Credential already revealed or expired.</div>"
    audit_service.log(
        action="TEMP_CREDENTIAL_REVEALED",
        resource_type="user",
        resource_id=id,
    )
    return (
        "<div class='alert alert-info'>"
        "<strong>One-time password (copy now - will not be shown again):</strong><br>"
        f"<code class='user-select-all fs-5'>{cred}</code>"
        "</div>"
    )
