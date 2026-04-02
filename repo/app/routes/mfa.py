from flask import Blueprint, render_template, request, session

from app.extensions import db
from app.services.decorators import high_risk_action, login_required
from app.services.mfa_service import (
    disable_mfa,
    enable_mfa,
    generate_qr_svg,
    generate_totp_secret,
    get_totp_uri,
    verify_totp_secret,
)
from app.services.session_service import get_current_user

mfa_bp = Blueprint("mfa", __name__, url_prefix="/settings/mfa")


@mfa_bp.get("")
@login_required
def mfa_settings():
    user = get_current_user()
    if not user:
        return "", 401
    return render_template("settings/mfa.html", user=user)


@mfa_bp.post("/setup")
@login_required
def mfa_setup():
    user = get_current_user()
    if not user:
        return "", 401
    temp_secret = generate_totp_secret()
    user.mfa_secret = temp_secret
    user.mfa_enabled = False
    db.session.add(user)
    db.session.commit()
    session["mfa_setup_secret"] = temp_secret

    otp_uri = get_totp_uri(user)
    qr_svg = generate_qr_svg(otp_uri)

    return render_template("settings/_mfa_setup.html", qr_svg=qr_svg, error_message="", success_message="")


@mfa_bp.get("/setup")
@login_required
def mfa_setup_page():
    user = get_current_user()
    if not user:
        return "", 401
    return render_template("settings/mfa.html", user=user)


@mfa_bp.post("/verify-setup")
@login_required
def mfa_verify_setup():
    user = get_current_user()
    if not user:
        return "", 401
    temp_secret = session.get("mfa_setup_secret") or user.mfa_secret
    code = (request.form.get("totp_code") or "").strip()

    if not temp_secret:
        return render_template(
            "settings/_mfa_setup.html",
            qr_svg="",
            error_message="MFA setup session expired. Please start again.",
            success_message="",
        )

    user.mfa_secret = temp_secret
    otp_uri = get_totp_uri(user)
    qr_svg = generate_qr_svg(otp_uri)

    if not verify_totp_secret(temp_secret, code):
        return render_template(
            "settings/_mfa_setup.html",
            qr_svg=qr_svg,
            error_message="Invalid code. Please try again.",
            success_message="",
        )

    enable_mfa(user, temp_secret)
    session.pop("mfa_setup_secret", None)
    return render_template(
        "settings/_mfa_setup.html",
        qr_svg="",
        error_message="",
        success_message="MFA enabled successfully.",
    )


@mfa_bp.post("/disable")
@login_required
@high_risk_action
def mfa_disable():
    user = get_current_user()
    if not user:
        return "", 401
    disable_mfa(user)
    return (
        "<div class='alert alert-success' role='alert'>MFA has been disabled.</div>"
        "<button class='btn btn-primary' hx-post='/settings/mfa/setup' hx-target='#mfa-setup-area' "
        "hx-swap='innerHTML'>Enable MFA</button>"
    )
