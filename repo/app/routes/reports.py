from flask import Blueprint, abort, render_template, request

from app.models.paper import Paper
from app.services import rbac_service, report_service
from app.services.decorators import login_required, permission_required, require_role
from app.services.session_service import get_active_role, get_current_user


def _report_perm_error(e: PermissionError):
    if e.args and e.args[0] == "not_found":
        abort(404)
    abort(403)


def _can_export(actor) -> bool:
    """dept_admin always gets export; others need the explicit permission."""
    return get_active_role() == "dept_admin" or rbac_service.has_permission(actor, "report:export")

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


def _paper_or_403(paper_id, actor):
    paper = Paper.query.get_or_404(paper_id)
    if not rbac_service.can_access_cohort(actor, paper.cohort_id, effective_role=get_active_role()):
        abort(403)
    return paper


@reports_bp.get("")
@login_required
@require_role("dept_admin", "faculty_advisor", "corporate_mentor")
def reports_index():
    actor = get_current_user()
    effective_role = get_active_role()
    accessible_cohort_ids = {c.id for c in rbac_service.get_accessible_cohorts(actor, effective_role=effective_role)}

    filter_cohort_id = request.args.get("cohort_id", type=int)
    if filter_cohort_id and filter_cohort_id in accessible_cohort_ids:
        cohort_ids = [filter_cohort_id]
        filtered_cohort = filter_cohort_id
    else:
        cohort_ids = list(accessible_cohort_ids)
        filtered_cohort = None

    papers = Paper.query.filter(Paper.cohort_id.in_(cohort_ids)).order_by(Paper.id.desc()).all() if cohort_ids else []
    return render_template("reports/index.html", papers=papers, filtered_cohort=filtered_cohort)


@reports_bp.get("/paper/<int:paper_id>")
@login_required
@require_role("dept_admin", "faculty_advisor", "corporate_mentor")
def paper_report(paper_id: int):
    actor = get_current_user()
    paper = _paper_or_403(paper_id, actor)
    return render_template("reports/paper.html", paper=paper)


@reports_bp.get("/paper/<int:paper_id>/summary")
@login_required
@require_role("dept_admin", "faculty_advisor", "corporate_mentor")
def summary_fragment(paper_id: int):
    actor = get_current_user()
    _paper_or_403(paper_id, actor)
    can_export = _can_export(actor)
    try:
        data = report_service.get_paper_score_summary(paper_id, actor, effective_role=get_active_role())
    except PermissionError as e:
        _report_perm_error(e)
    return render_template("reports/_summary.html", data=data, can_export=can_export)


@reports_bp.get("/paper/<int:paper_id>/difficulty")
@login_required
@require_role("dept_admin", "faculty_advisor", "corporate_mentor")
def difficulty_fragment(paper_id: int):
    actor = get_current_user()
    _paper_or_403(paper_id, actor)
    can_export = _can_export(actor)
    try:
        data = report_service.get_item_difficulty(paper_id, actor, effective_role=get_active_role())
    except PermissionError as e:
        _report_perm_error(e)
    return render_template("reports/_difficulty.html", rows=data, can_export=can_export, paper_id=paper_id)


@reports_bp.get("/paper/<int:paper_id>/cohort-comparison")
@login_required
@require_role("dept_admin", "faculty_advisor", "corporate_mentor")
def cohort_comparison_fragment(paper_id: int):
    actor = get_current_user()
    _paper_or_403(paper_id, actor)
    can_export = _can_export(actor)
    try:
        data = report_service.get_cohort_comparison(paper_id, actor, effective_role=get_active_role())
    except PermissionError as e:
        _report_perm_error(e)
    return render_template("reports/_cohort_comparison.html", rows=data, can_export=can_export, paper_id=paper_id)


@reports_bp.get("/paper/<int:paper_id>/students")
@login_required
@require_role("dept_admin", "faculty_advisor", "corporate_mentor")
def students_fragment(paper_id: int):
    actor = get_current_user()
    paper = _paper_or_403(paper_id, actor)
    can_export = _can_export(actor)
    try:
        data = report_service.get_student_results(paper.cohort_id, paper.id, actor, effective_role=get_active_role())
    except PermissionError as e:
        _report_perm_error(e)
    return render_template("reports/_students.html", rows=data, can_export=can_export)


@reports_bp.get("/paper/<int:paper_id>/export/summary")
@login_required
@require_role("dept_admin", "faculty_advisor", "corporate_mentor")
@permission_required("report:export")
def export_summary(paper_id: int):
    actor = get_current_user()
    _paper_or_403(paper_id, actor)
    try:
        data = report_service.get_paper_score_summary(paper_id, actor, effective_role=get_active_role())
    except PermissionError as e:
        _report_perm_error(e)
    rows = [
        {
            "paper_id": paper_id,
            "total_assigned": data["total_assigned"],
            "attempted": data["attempted"],
            "submitted": data["submitted"],
            "average_score": data["average_score"],
            "highest_score": data["highest_score"],
            "lowest_score": data["lowest_score"],
            "pass_rate": data["pass_rate"],
        }
    ]
    return report_service.export_to_csv(rows, f"report_{paper_id}_summary")


@reports_bp.get("/paper/<int:paper_id>/export/students")
@login_required
@require_role("dept_admin", "faculty_advisor", "corporate_mentor")
@permission_required("report:export")
def export_students(paper_id: int):
    actor = get_current_user()
    paper = _paper_or_403(paper_id, actor)
    try:
        rows = report_service.get_student_results(paper.cohort_id, paper.id, actor, effective_role=get_active_role())
    except PermissionError as e:
        _report_perm_error(e)
    return report_service.export_to_csv(rows, f"report_{paper_id}_students")


@reports_bp.get("/paper/<int:paper_id>/export/difficulty")
@login_required
@require_role("dept_admin", "faculty_advisor", "corporate_mentor")
@permission_required("report:export")
def export_difficulty(paper_id: int):
    actor = get_current_user()
    _paper_or_403(paper_id, actor)
    try:
        rows = report_service.get_item_difficulty(paper_id, actor, effective_role=get_active_role())
    except PermissionError as e:
        _report_perm_error(e)
    return report_service.export_to_csv(rows, f"report_{paper_id}_difficulty")


@reports_bp.get("/paper/<int:paper_id>/export/cohort-comparison")
@login_required
@require_role("dept_admin", "faculty_advisor", "corporate_mentor")
@permission_required("report:export")
def export_cohort_comparison(paper_id: int):
    actor = get_current_user()
    _paper_or_403(paper_id, actor)
    try:
        rows = report_service.get_cohort_comparison(paper_id, actor, effective_role=get_active_role())
    except PermissionError as e:
        _report_perm_error(e)
    return report_service.export_to_csv(rows, f"report_{paper_id}_cohort_comparison")


@reports_bp.get("/paper/<int:paper_id>/export")
@login_required
@require_role("dept_admin", "faculty_advisor", "corporate_mentor")
@permission_required("report:export")
def export_default(paper_id: int):
    actor = get_current_user()
    paper = _paper_or_403(paper_id, actor)
    try:
        rows = report_service.get_student_results(paper.cohort_id, paper.id, actor, effective_role=get_active_role())
    except PermissionError as e:
        _report_perm_error(e)
    return report_service.export_to_csv(rows, f"report_{paper_id}_students")
