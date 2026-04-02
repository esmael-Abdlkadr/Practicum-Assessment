from app.routes.admin import admin_bp
from app.routes.auth import auth_bp
from app.routes.cohort import cohort_bp
from app.routes.main import main_bp
from app.routes.mfa import mfa_bp
from app.routes.org import org_bp
from app.routes.papers import papers_bp
from app.routes.permissions import permissions_bp
from app.routes.questions import questions_bp
from app.routes.quiz import quiz_bp
from app.routes.grading import grading_bp
from app.routes.reports import reports_bp
from app.routes.admin_users import admin_users_bp
from app.routes.assignments import assignments_bp


def register_blueprints(app):
    app.register_blueprint(admin_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(cohort_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(mfa_bp)
    app.register_blueprint(org_bp)
    app.register_blueprint(papers_bp)
    app.register_blueprint(permissions_bp)
    app.register_blueprint(questions_bp)
    app.register_blueprint(quiz_bp)
    app.register_blueprint(grading_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(admin_users_bp)
    app.register_blueprint(assignments_bp)
