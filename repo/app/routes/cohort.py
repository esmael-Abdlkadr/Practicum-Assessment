from flask import Blueprint, render_template

from app.models.org import Cohort
from app.services import rbac_service
from app.services.decorators import login_required, permission_required, require_scope
from app.services.session_service import get_active_role, get_current_user

cohort_bp = Blueprint("cohort", __name__)


@cohort_bp.get("/cohorts")
@login_required
def my_cohorts():
    user = get_current_user()
    effective_role = get_active_role()
    cohorts = rbac_service.get_accessible_cohorts(user, effective_role=effective_role) if user else []
    return render_template("cohorts/list.html", user=user, cohorts=cohorts)


@cohort_bp.get("/cohorts/<int:cohort_id>")
@login_required
@require_scope("cohort", "cohort_id")
@permission_required("cohort:view")
def cohort_detail(cohort_id: int):
    cohort = Cohort.query.get_or_404(cohort_id)
    return render_template("cohorts/detail.html", cohort=cohort)
