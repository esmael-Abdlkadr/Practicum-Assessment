import bcrypt

from app import create_app
from app.extensions import db
from app.models.user import User


def seed_db() -> bool:
    """Create demo accounts only if they do not already exist.

    Existing accounts are never touched so that real operational state
    (custom passwords, lock state, MFA settings) is preserved across restarts.
    """
    defaults = [
        ("admin", "Admin@Practicum1", "dept_admin"),
        ("advisor1", "Advisor@Practicum1", "faculty_advisor"),
        ("mentor1", "Mentor@Practicum1", "corporate_mentor"),
        ("student1", "Student@Practicum1", "student"),
        ("student2", "Student@Practicum1", "student"),
    ]
    changed_any = False
    for username, password, role in defaults:
        if User.query.filter_by(username=username).first():
            continue
        user = User(
            username=username,
            role=role,
            is_active=True,
            failed_attempts=0,
            locked_until=None,
            force_password_change=False,
        )
        user.password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        db.session.add(user)
        changed_any = True

    db.session.commit()
    return changed_any


def seed_admin() -> bool:
    return seed_db()


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        seed_db()
