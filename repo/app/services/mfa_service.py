from io import BytesIO

import pyotp
import qrcode
import qrcode.image.svg

from app.extensions import db
from app.models.user import User
from app.services import audit_service


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def get_totp_uri(user: User) -> str:
    if not user.mfa_secret:
        raise ValueError("MFA secret not set")
    return pyotp.totp.TOTP(user.mfa_secret).provisioning_uri(name=user.username, issuer_name="Practicum System")


def generate_qr_svg(uri: str) -> str:
    image = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage)
    buffer = BytesIO()
    image.save(buffer)
    return buffer.getvalue().decode("utf-8")


def verify_totp(user: User, code: str) -> bool:
    if not user or not user.mfa_secret:
        return False
    return bool(pyotp.TOTP(user.mfa_secret).verify((code or "").strip(), valid_window=1))


def verify_totp_secret(secret: str, code: str) -> bool:
    if not secret:
        return False
    return bool(pyotp.TOTP(secret).verify((code or "").strip(), valid_window=1))


def enable_mfa(user: User, secret: str):
    user.mfa_secret = secret
    user.mfa_enabled = True
    db.session.add(user)
    db.session.commit()
    audit_service.log(action="MFA_ENABLED", resource_type="user", resource_id=user.id)


def disable_mfa(user: User):
    user.mfa_secret = None
    user.mfa_enabled = False
    db.session.add(user)
    db.session.commit()
    audit_service.log(action="MFA_DISABLED", resource_type="user", resource_id=user.id)
