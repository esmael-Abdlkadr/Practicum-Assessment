import os
import json
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()
from flask import Flask, redirect, render_template, request, session, url_for
from sqlalchemy import text

from app.config import config_by_name
from app.extensions import csrf, db, login_manager, session_manager
from app.routes import register_blueprints
from app.services import rbac_service
from app.services import session_service


def _normalize_sqlite_uri(db_uri: str, app_root: Path) -> str:
    if not db_uri or not db_uri.startswith("sqlite:///"):
        return db_uri

    # Special case: in-memory DB used for testing - must not be modified.
    if db_uri == "sqlite:///:memory:":
        return db_uri

    if db_uri.startswith("sqlite:////"):
        absolute_path = Path(db_uri.replace("sqlite:////", "/", 1))
    else:
        relative_path = db_uri.replace("sqlite:///", "", 1)
        absolute_path = app_root.joinpath(relative_path)

    absolute_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:////{absolute_path}"


def create_app(config_name: str = "development") -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_by_name.get(config_name, config_by_name["development"]))

    app.config["SESSION_TYPE"] = os.environ.get("SESSION_TYPE", app.config.get("SESSION_TYPE", "filesystem"))
    app.config["SESSION_FILE_DIR"] = os.environ.get("SESSION_FILE_DIR", "/tmp/flask_session")
    os.makedirs(app.config["SESSION_FILE_DIR"], exist_ok=True)
    lifetime_minutes = int(os.environ.get("SESSION_LIFETIME_MINUTES", "30"))
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=lifetime_minutes)

    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    app.config["SQLALCHEMY_DATABASE_URI"] = _normalize_sqlite_uri(db_uri, Path(app.root_path).parent)

    db.init_app(app)
    login_manager.init_app(app)
    session_manager.init_app(app)
    csrf.init_app(app)

    @login_manager.user_loader
    def _load_user(_user_id):
        return None

    register_blueprints(app)

    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("errors/404.html"), 404

    @app.context_processor
    def _nav_sections_context():
        user = session_service.get_current_user()
        return {"nav_sections": rbac_service.get_nav_for_role(user, active_role=session_service.get_active_role())}

    @app.template_filter("fromjson")
    def _fromjson_filter(value):
        if not value:
            return []
        if isinstance(value, (list, dict)):
            return value
        try:
            return json.loads(value)
        except Exception:
            return []

    _CHANGE_PASSWORD_EXEMPT = frozenset({
        "auth.change_password_page",
        "auth.change_password_submit",
        "auth.logout",
        "auth.login_page",
        "auth.login_submit",
        "auth.login_mfa_page",
        "auth.login_mfa_submit",
        "auth.reauth_page",
        "auth.reauth_submit",
        "static",
        "main.health",
        "main.client_error_log",
    })

    @app.before_request
    def _session_lifecycle() -> None:
        session.permanent = True

        if request.endpoint == "static" or request.path == "/health":
            return None

        from app.services import attempt_service

        attempt_service.check_expired_attempts()

        if session.get("user_id") and session_service.is_session_expired():
            session_service.logout_user()
            return redirect(url_for("auth.login_page", reason="expired"))

        if session.get("user_id") and request.endpoint not in _CHANGE_PASSWORD_EXEMPT:
            user = session_service.get_current_user()
            if user and user.force_password_change:
                return redirect(url_for("auth.change_password_page"))

        last_run = app.config.get("LAST_DELEGATION_EXPIRY")
        now = session_service._utcnow()
        if not last_run or (now - last_run).total_seconds() >= 3600:
            rbac_service.expire_delegations()
            app.config["LAST_DELEGATION_EXPIRY"] = now

        last_purge = app.config.get("LAST_AUDIT_PURGE")
        if not last_purge or (now - last_purge).total_seconds() >= 86400:
            from app.services import audit_service as _audit_svc

            _audit_svc.purge_old_logs()
            app.config["LAST_AUDIT_PURGE"] = now

        session_service.refresh_activity()
        return None

    @app.after_request
    def _no_store_headers(response):
        """Prevent browsers from caching authenticated HTML pages."""
        if request.endpoint == "static":
            return response
        if response.content_type and response.content_type.startswith("text/html"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    with app.app_context():
        from app import models as _models  # noqa: F401

        db.create_all()
        from app.services.org_setup import ensure_department_hierarchy

        ensure_department_hierarchy()
        columns = db.session.execute(text("PRAGMA table_info(users)")).fetchall()
        column_names = {row[1] for row in columns}
        if "force_password_change" not in column_names:
            db.session.execute(text("ALTER TABLE users ADD COLUMN force_password_change BOOLEAN DEFAULT 0"))
            db.session.commit()
        rbac_service.expire_delegations()
        app.config["LAST_DELEGATION_EXPIRY"] = session_service._utcnow()
        app.config["LAST_AUDIT_PURGE"] = session_service._utcnow()

    return app
