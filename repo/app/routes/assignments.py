from datetime import datetime, timezone

from flask import Blueprint, abort, render_template, request

from app.models.assignment import Assignment, AssignmentGrade, AssignmentSubmission
from app.models.org import Cohort
from app.services import assignment_service, audit_service, rbac_service
from app.services.decorators import login_required, require_role
from app.services.session_service import get_active_role, get_current_user

assignments_bp = Blueprint("assignments", __name__)


def _cohort_name_map():
    return {c.id: c.name for c in Cohort.query.order_by(Cohort.id.asc()).all()}


@assignments_bp.get("/admin/assignments")
@login_required
@require_role("dept_admin")
def admin_assignment_list():
    cohort_id = request.args.get("cohort_id")
    cid = int(cohort_id) if cohort_id and cohort_id.isdigit() else None
    rows = assignment_service.get_assignment_list_for_admin(cid)
    cohorts = Cohort.query.order_by(Cohort.id.desc()).all()
    return render_template(
        "admin/assignments/list.html",
        assignments=rows,
        cohorts=cohorts,
        cohort_name_map=_cohort_name_map(),
    )


@assignments_bp.get("/admin/assignments/new")
@login_required
@require_role("dept_admin")
def admin_assignment_new_form():
    cohorts = Cohort.query.order_by(Cohort.id.desc()).all()
    return render_template("admin/assignments/_form.html", cohorts=cohorts)


@assignments_bp.post("/admin/assignments")
@login_required
@require_role("dept_admin")
def admin_assignment_create():
    actor = get_current_user()
    try:
        assignment = assignment_service.create_assignment(
            title=request.form.get("title") or "",
            description=request.form.get("description") or "",
            cohort_id=int(request.form.get("cohort_id") or 0),
            creator_id=actor.id,
            due_date_str=(request.form.get("due_date") or "").strip() or None,
            max_score=float(request.form.get("max_score") or 100),
        )
    except ValueError as exc:
        return f"<div class='alert alert-danger' role='alert'>{str(exc)}</div>", 400

    audit_service.log(
        action="ASSIGNMENT_CREATED",
        resource_type="assignment",
        resource_id=assignment.id,
    )
    return render_template(
        "admin/assignments/_row.html",
        assignment=assignment,
        cohort_name=(_cohort_name_map().get(assignment.cohort_id) or f"#{assignment.cohort_id}"),
    )


@assignments_bp.post("/admin/assignments/<int:id>/publish")
@login_required
@require_role("dept_admin")
def admin_assignment_publish(id: int):
    try:
        assignment = assignment_service.publish_assignment(id)
    except ValueError as exc:
        return f"<div class='alert alert-danger' role='alert'>{str(exc)}</div>", 400
    audit_service.log(
        action="ASSIGNMENT_PUBLISHED",
        resource_type="assignment",
        resource_id=id,
    )
    return render_template(
        "admin/assignments/_row.html",
        assignment=assignment,
        cohort_name=(_cohort_name_map().get(assignment.cohort_id) or f"#{assignment.cohort_id}"),
    )


@assignments_bp.post("/admin/assignments/<int:id>/close")
@login_required
@require_role("dept_admin")
def admin_assignment_close(id: int):
    try:
        assignment = assignment_service.close_assignment(id)
    except ValueError as exc:
        return f"<div class='alert alert-danger' role='alert'>{str(exc)}</div>", 400
    audit_service.log(
        action="ASSIGNMENT_CLOSED",
        resource_type="assignment",
        resource_id=id,
    )
    return render_template(
        "admin/assignments/_row.html",
        assignment=assignment,
        cohort_name=(_cohort_name_map().get(assignment.cohort_id) or f"#{assignment.cohort_id}"),
    )


@assignments_bp.get("/assignments")
@login_required
@require_role("student")
def student_assignments_list():
    student = get_current_user()
    rows = assignment_service.get_assignments_for_student(student)
    return render_template("assignments/list.html", assignments=rows, cohort_name_map=_cohort_name_map())


@assignments_bp.get("/assignments/<int:id>")
@login_required
@require_role("student")
def student_assignment_detail(id: int):
    student = get_current_user()
    try:
        assignment = assignment_service.get_assignment_for_student(id, student)
    except PermissionError:
        return abort(403)

    submission = AssignmentSubmission.query.filter_by(assignment_id=assignment.id, student_id=student.id).first()
    if not submission:
        if assignment.status != "published":
            return abort(403)
        submission = assignment_service.get_or_create_draft(assignment.id, student.id)

    grade = AssignmentGrade.query.filter_by(submission_id=submission.id).first()
    return render_template("assignments/detail.html", assignment=assignment, submission=submission, grade=grade)


@assignments_bp.post("/assignments/<int:id>/save")
@login_required
@require_role("student")
def student_assignment_save(id: int):
    student = get_current_user()
    try:
        assignment = assignment_service.get_assignment_for_student(id, student)
    except PermissionError:
        return abort(403)
    if assignment.status != "published":
        return "<div class='alert alert-danger' role='alert'>Assignment is not open for edits.</div>", 400

    submission = assignment_service.get_or_create_draft(assignment.id, student.id)
    try:
        assignment_service.save_draft(submission.id, request.form.get("content") or "", student)
    except ValueError as exc:
        return f"<div class='alert alert-danger' role='alert'>{str(exc)}</div>", 400

    audit_service.log(
        action="ASSIGNMENT_DRAFT_SAVED",
        resource_type="assignment_submission",
        resource_id=submission.id,
    )
    stamp = datetime.now(timezone.utc).replace(tzinfo=None).strftime("%H:%M")
    return f"<div id='save-status'>Saved at {stamp}</div>"


@assignments_bp.post("/assignments/<int:id>/submit")
@login_required
@require_role("student")
def student_assignment_submit(id: int):
    student = get_current_user()
    try:
        assignment = assignment_service.get_assignment_for_student(id, student)
    except PermissionError:
        return abort(403)
    if assignment.status != "published":
        return "<div class='alert alert-danger' role='alert'>Assignment is not accepting submissions.</div>", 400

    submission = assignment_service.get_or_create_draft(assignment.id, student.id)
    try:
        assignment_service.save_draft(submission.id, request.form.get("content") or "", student)
        submission = assignment_service.submit(submission.id, student)
    except ValueError as exc:
        return f"<div class='alert alert-danger' role='alert'>{str(exc)}</div>", 400

    audit_service.log(
        action="ASSIGNMENT_SUBMITTED",
        resource_type="assignment_submission",
        resource_id=submission.id,
    )
    return (
        "<div class='alert alert-success' role='alert'>"
        "Submission received successfully."
        "</div>"
    )


@assignments_bp.get("/assignments/grading")
@login_required
@require_role("faculty_advisor", "corporate_mentor")
def grader_assignment_list():
    grader = get_current_user()
    rows = assignment_service.get_submissions_for_grader(grader, effective_role=get_active_role())
    return render_template("assignments/grading/list.html", rows=rows, cohort_name_map=_cohort_name_map())


@assignments_bp.get("/assignments/grading/<int:submission_id>")
@login_required
@require_role("faculty_advisor", "corporate_mentor")
def grader_assignment_detail(submission_id: int):
    grader = get_current_user()
    submission = AssignmentSubmission.query.get_or_404(submission_id)
    assignment = Assignment.query.get_or_404(submission.assignment_id)
    if not rbac_service.can_access_cohort(grader, assignment.cohort_id, effective_role=get_active_role()):
        return abort(403)
    grade = AssignmentGrade.query.filter_by(submission_id=submission.id).first()
    return render_template("assignments/grading/detail.html", submission=submission, assignment=assignment, grade=grade)


@assignments_bp.post("/assignments/grading/<int:submission_id>/grade")
@login_required
@require_role("faculty_advisor", "corporate_mentor")
def grader_assignment_grade(submission_id: int):
    grader = get_current_user()
    feedback = request.form.get("feedback") or ""
    score = request.form.get("score") or ""
    try:
        grade = assignment_service.grade_submission(submission_id, float(score), feedback, grader, effective_role=get_active_role())
    except PermissionError:
        return abort(403)
    except ValueError as exc:
        return f"<div class='alert alert-danger' role='alert'>{str(exc)}</div>", 400

    assignment = Assignment.query.get_or_404(AssignmentSubmission.query.get_or_404(submission_id).assignment_id)
    audit_service.log(
        action="ASSIGNMENT_GRADED",
        resource_type="assignment_grade",
        resource_id=grade.id,
    )
    return render_template(
        "assignments/grading/_grade_form.html",
        submission_id=submission_id,
        assignment=assignment,
        grade=grade,
    )
