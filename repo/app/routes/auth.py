from flask import Blueprint, make_response, redirect, render_template, request, session, url_for
from datetime import datetime, timezone

from app.extensions import db
from app.services.auth_service import (
    authenticate,
    generate_captcha,
    is_account_locked,
    lock_account,
    record_login_attempt,
    requires_captcha,
    verify_captcha,
    verify_password,
)
from app.services.decorators import high_risk_action, login_required
from app.services.mfa_service import verify_totp
from app.services import audit_service
from app.services.session_service import (
    confirm_reauth,
    get_active_role,
    get_current_user,
    login_user,
    logout_user,
)
from app.models.user import User
from app.models.org import School, Major, Cohort
from app.models.assignment import CohortMember
from app.models.audit_log import AuditLog
from app.models.paper import Paper
from app.models.attempt import Attempt
from app.services import rbac_service

auth_bp = Blueprint("auth", __name__)


def _client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _render_login_fragment(error_message: str = "", username: str = ""):
    need_captcha = requires_captcha(username)
    captcha_question = ""

    if need_captcha:
        captcha_question = session.get("captcha_question", "")
        if not captcha_question:
            captcha_question, expected = generate_captcha()
            session["captcha_question"] = captcha_question
            session["captcha_expected"] = expected
    else:
        session.pop("captcha_question", None)
        session.pop("captcha_expected", None)

    return render_template(
        "auth/_login_error.html",
        error_message=error_message,
        username=username,
        requires_captcha=need_captcha,
        captcha_question=captcha_question,
    )


@auth_bp.get("/login")
def login_page():
    reason = request.args.get("reason", "")
    expired_message = "Your session expired. Please sign in again." if reason == "expired" else ""
    return render_template(
        "auth/login.html",
        error_message="",
        username="",
        requires_captcha=False,
        captcha_question="",
        expired_message=expired_message,
    )


@auth_bp.post("/login")
def login_submit():
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    captcha_answer = request.form.get("captcha_answer") or ""

    if requires_captcha(username):
        user_for_captcha = User.query.filter_by(username=username).first()
        if user_for_captcha and is_account_locked(user_for_captcha):
            record_login_attempt(username=username, ip=_client_ip(), success=False)
            return _render_login_fragment(error_message="Account locked for 15 minutes.", username=username)

        expected = session.get("captcha_expected", "")
        if not expected or not verify_captcha(captcha_answer, expected):
            if user_for_captcha:
                user_for_captcha.failed_attempts = (user_for_captcha.failed_attempts or 0) + 1
                db.session.add(user_for_captcha)
                if user_for_captcha.failed_attempts >= 8:
                    lock_account(user_for_captcha)
                    record_login_attempt(username=username, ip=_client_ip(), success=False)
                    return _render_login_fragment(error_message="Account locked for 15 minutes.", username=username)
                db.session.commit()
            record_login_attempt(username=username, ip=_client_ip(), success=False)
            return _render_login_fragment(
                error_message="Incorrect CAPTCHA answer.",
                username=username,
            )

    user, error = authenticate(username=username, password=password, ip=_client_ip())
    if not user:
        if error == "mfa_required":
            if request.headers.get("HX-Request") == "true":
                response = make_response("", 204)
                response.headers["HX-Redirect"] = url_for("auth.login_mfa_page")
                return response
            return redirect(url_for("auth.login_mfa_page"))
        return _render_login_fragment(error_message=error, username=username)

    session.pop("captcha_question", None)
    session.pop("captcha_expected", None)
    login_user(user)

    if request.headers.get("HX-Request") == "true":
        response = make_response("", 204)
        response.headers["HX-Redirect"] = url_for("auth.dashboard")
        return response

    return redirect(url_for("auth.dashboard"))


@auth_bp.get("/logout")
def logout():
    if session.get("user_id"):
        audit_service.log(action="LOGOUT", resource_type="session", resource_id=session.get("user_id"))
    logout_user()
    return redirect(url_for("auth.login_page"))


@auth_bp.get("/login/mfa")
def login_mfa_page():
    if not session.get("mfa_pending_user_id"):
        return redirect(url_for("auth.login_page"))
    return render_template("auth/mfa_verify.html", error_message="")


@auth_bp.post("/login/mfa")
def login_mfa_submit():
    pending_user_id = session.get("mfa_pending_user_id")
    if not pending_user_id:
        return redirect(url_for("auth.login_page"))

    code = (request.form.get("totp_code") or "").strip()
    user = db.session.get(User, pending_user_id)
    if not user or not verify_totp(user, code):
        record_login_attempt(username=session.get("pending_username", "unknown"), ip=_client_ip(), success=False)
        audit_service.log(
            action="LOGIN_FAILED_MFA",
            resource_type="user",
            resource_id=pending_user_id,
            extra={"reason": "invalid_totp"},
        )
        return render_template("auth/mfa_verify.html", error_message="Invalid MFA code.")

    login_user(user)
    user.last_login_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.session.add(user)
    db.session.commit()
    session.pop("mfa_pending_user_id", None)
    session.pop("pending_username", None)
    record_login_attempt(username=user.username, ip=_client_ip(), success=True)
    audit_service.log(action="LOGIN_SUCCESS", resource_type="user", resource_id=user.id)

    if request.headers.get("HX-Request") == "true":
        response = make_response("", 204)
        response.headers["HX-Redirect"] = url_for("auth.dashboard")
        return response
    return redirect(url_for("auth.dashboard"))


@auth_bp.get("/reauth")
@login_required
def reauth_page():
    next_url = request.args.get("next") or session.get("reauth_next") or url_for("auth.dashboard")
    session["reauth_next"] = next_url
    return render_template("auth/reauth.html", error_message="", next_url=next_url)


@auth_bp.post("/reauth")
@login_required
def reauth_submit():
    user = get_current_user()
    password = request.form.get("password") or ""
    next_url = request.form.get("next_url") or session.get("reauth_next") or url_for("auth.dashboard")
    action = session.get("reauth_required_for") or "high_risk"

    if not user or not verify_password(password, user.password_hash):
        audit_service.log(action="REAUTH_FAILED", resource_type="user", resource_id=session.get("user_id"))
        return render_template(
            "auth/reauth.html",
            error_message="Password confirmation failed.",
            next_url=next_url,
        )

    confirm_reauth(action)
    audit_service.log(action="REAUTH_SUCCESS", resource_type="user", resource_id=session.get("user_id"))
    session.pop("reauth_required_for", None)
    session.pop("reauth_next", None)

    if request.headers.get("HX-Request") == "true":
        response = make_response("", 204)
        response.headers["HX-Redirect"] = next_url
        return response

    return redirect(next_url)


@auth_bp.get("/change-password")
@login_required
def change_password_page():
    return render_template("auth/change_password.html", error_message="")


@auth_bp.post("/change-password")
@login_required
def change_password_submit():
    from app.services.auth_service import hash_password, validate_password_strength

    user = get_current_user()
    new_password = request.form.get("new_password") or ""
    confirm_password = request.form.get("confirm_password") or ""

    if new_password != confirm_password:
        return render_template("auth/change_password.html", error_message="Passwords do not match.")

    ok, error = validate_password_strength(new_password)
    if not ok:
        return render_template("auth/change_password.html", error_message=error)

    user.password_hash = hash_password(new_password)
    user.force_password_change = False
    from app.extensions import db
    db.session.add(user)
    db.session.commit()
    audit_service.log(action="PASSWORD_CHANGED", resource_type="user", resource_id=user.id)

    if request.headers.get("HX-Request") == "true":
        response = make_response("", 204)
        response.headers["HX-Redirect"] = url_for("auth.dashboard")
        return response
    return redirect(url_for("auth.dashboard"))


@auth_bp.get("/dashboard")
@login_required
def dashboard():
    user = get_current_user()
    if not user:
        return redirect(url_for("auth.login_page"))
    active_role = get_active_role()
    context = {
        "user": user,
        "active_role": active_role,
        "admin_counts": {},
        "recent_audit_events": [],
        "assigned_cohorts": [],
        "pending_grading_count": 0,
        "student_assessments": [],
    }

    if active_role == "dept_admin":
        context["admin_counts"] = {
            "schools": School.query.count(),
            "majors": Major.query.count(),
            "cohorts": Cohort.query.count(),
            "users": User.query.count(),
        }
        context["recent_audit_events"] = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(10).all()
    elif active_role in {"faculty_advisor", "corporate_mentor"}:
        context["assigned_cohorts"] = rbac_service.get_accessible_cohorts(user, effective_role=active_role)
        accessible_cohort_ids = [c.id for c in context["assigned_cohorts"]]
        context["pending_grading_count"] = (
            Attempt.query
            .join(Paper, Paper.id == Attempt.paper_id)
            .filter(
                Paper.cohort_id.in_(accessible_cohort_ids),
                Attempt.status == "submitted",
            )
            .count()
        ) if accessible_cohort_ids else 0
    elif active_role == "student":
        assignments = CohortMember.query.filter_by(user_id=user.id, role_in_cohort="student").all()
        cohort_ids = [row.cohort_id for row in assignments]
        papers = (
            Paper.query.filter(Paper.cohort_id.in_(cohort_ids), Paper.status == "published")
            .order_by(Paper.id.desc())
            .all()
        )
        context["student_assessments"] = [
            {"cohort_id": p.cohort_id, "paper_title": p.title, "status": "not started"} for p in papers
        ]

    return render_template("dashboard.html", **context)


@auth_bp.get("/switch-role")
@login_required
def switch_role_page():
    user = get_current_user()
    if not user:
        return redirect(url_for("auth.login_page"))
    available = rbac_service.get_available_roles(user)
    current = get_active_role()
    return render_template("auth/switch_role.html", available=available, current=current)


@auth_bp.post("/switch-role")
@login_required
@high_risk_action
def switch_role_submit():
    user = get_current_user()
    if not user:
        return redirect(url_for("auth.login_page"))
    requested = (request.form.get("role") or "").strip()
    available = rbac_service.get_available_roles(user)
    if requested not in available:
        return "<div class='alert alert-danger'>Role not available.</div>", 403
    old_role = get_active_role()
    session["active_role"] = requested
    audit_service.log(
        action="ROLE_SWITCHED",
        resource_type="session",
        resource_id=user.id,
        old_value={"role": old_role},
        new_value={"role": requested},
    )
    if request.headers.get("HX-Request") == "true":
        response = make_response("", 204)
        response.headers["HX-Redirect"] = url_for("auth.dashboard")
        return response
    return redirect(url_for("auth.dashboard"))
