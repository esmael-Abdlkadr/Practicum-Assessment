import json

from flask import Blueprint, abort, render_template, request

from app.extensions import db
from app.models.assignment import CohortMember
from app.models.attempt import Attempt, AttemptAnswer
from app.models.grading import GradingResult, Rubric
from app.models.paper import Paper, PaperQuestion
from app.models.question import Question
from app.models.user import User
from app.services import grading_service, rbac_service
from app.services.decorators import login_required, require_role
from app.services.session_service import get_active_role, get_current_user

grading_bp = Blueprint("grading", __name__, url_prefix="/grading")


def _ensure_grader_can_access_attempt(grader, attempt):
    paper = Paper.query.get_or_404(attempt.paper_id)
    if not rbac_service.can_access_cohort(grader, paper.cohort_id, effective_role=get_active_role()):
        abort(403)
    return paper


@grading_bp.get("")
@login_required
@require_role("faculty_advisor", "corporate_mentor")
def dashboard():
    grader = get_current_user()
    pending = grading_service.get_pending_grading(grader, effective_role=get_active_role())
    return render_template("grading/dashboard.html", pending=pending)


@grading_bp.get("/paper/<int:paper_id>")
@login_required
@require_role("faculty_advisor", "corporate_mentor")
def paper_students(paper_id: int):
    grader = get_current_user()
    paper = Paper.query.get_or_404(paper_id)
    if not rbac_service.can_access_cohort(grader, paper.cohort_id, effective_role=get_active_role()):
        return abort(403)

    filter_mode = (request.args.get("filter") or "all").strip()
    attempts = Attempt.query.filter_by(paper_id=paper_id).order_by(Attempt.id.desc()).all()
    rows = []
    for attempt in attempts:
        pending_count = GradingResult.query.filter_by(attempt_id=attempt.id, status="pending").count()
        if filter_mode == "pending" and pending_count == 0:
            continue
        if filter_mode == "graded" and pending_count > 0:
            continue
        student = db.session.get(User, attempt.student_id)
        rows.append(
            {
                "attempt": attempt,
                "student": student,
                "pending_count": pending_count,
            }
        )

    return render_template("grading/paper_students.html", paper=paper, rows=rows, filter_mode=filter_mode)


@grading_bp.get("/attempt/<int:attempt_id>")
@login_required
@require_role("faculty_advisor", "corporate_mentor")
def grade_attempt(attempt_id: int):
    grader = get_current_user()
    attempt = Attempt.query.get_or_404(attempt_id)
    paper = _ensure_grader_can_access_attempt(grader, attempt)

    rows = (
        db.session.query(PaperQuestion, Question)
        .join(Question, Question.id == PaperQuestion.question_id)
        .filter(PaperQuestion.paper_id == paper.id)
        .order_by(PaperQuestion.order_index.asc())
        .all()
    )
    answers = {a.question_id: a for a in AttemptAnswer.query.filter_by(attempt_id=attempt.id).all()}
    grading = {g.question_id: g for g in GradingResult.query.filter_by(attempt_id=attempt.id).all()}
    rubrics = {r.question_id: r for r in Rubric.query.filter(Rubric.question_id.in_([q.id for _, q in rows])).all()}
    comments = {
        q.id: grading_service.get_comments(attempt.id, q.id, grader)
        for _, q in rows
    }
    return render_template(
        "grading/attempt.html",
        attempt=attempt,
        paper=paper,
        rows=rows,
        answers=answers,
        grading=grading,
        rubrics=rubrics,
        comments=comments,
    )


@grading_bp.post("/attempt/<int:attempt_id>/question/<int:question_id>/score")
@login_required
@require_role("faculty_advisor", "corporate_mentor")
def save_manual_score(attempt_id: int, question_id: int):
    grader = get_current_user()
    attempt = Attempt.query.get_or_404(attempt_id)
    _ensure_grader_can_access_attempt(grader, attempt)
    score = request.form.get("score")
    try:
        result = grading_service.grade_answer(attempt_id, question_id, score, grader, effective_role=get_active_role())
    except PermissionError:
        return abort(403)
    except ValueError as exc:
        return f"<div class='alert alert-danger' role='alert'>{str(exc)}</div>", 400

    question = Question.query.get_or_404(question_id)
    answer = AttemptAnswer.query.filter_by(attempt_id=attempt_id, question_id=question_id).first()
    rubric = Rubric.query.filter_by(question_id=question_id).first()
    comments = grading_service.get_comments(attempt_id, question_id, grader)
    link = PaperQuestion.query.filter_by(paper_id=attempt.paper_id, question_id=question_id).first()
    return render_template(
        "grading/_question_row.html",
        attempt=attempt,
        q=question,
        link=link,
        answer=answer,
        grade=result,
        rubric=rubric,
        comments=comments,
    )


@grading_bp.post("/attempt/<int:attempt_id>/question/<int:question_id>/comment")
@login_required
@require_role("faculty_advisor", "corporate_mentor")
def add_comment(attempt_id: int, question_id: int):
    grader = get_current_user()
    attempt = Attempt.query.get_or_404(attempt_id)
    _ensure_grader_can_access_attempt(grader, attempt)

    text = (request.form.get("comment_text") or "").strip()
    is_internal = request.form.get("is_internal") == "on"
    parent_id_raw = request.form.get("parent_id")
    parent_id = int(parent_id_raw) if parent_id_raw and parent_id_raw.isdigit() else None
    if not text:
        return abort(400)
    try:
        grading_service.add_comment(
            attempt_id,
            question_id,
            text,
            grader,
            is_internal,
            parent_id=parent_id,
        )
    except ValueError as exc:
        return f"<div class='alert alert-danger'>{exc}</div>", 400
    comments = grading_service.get_comments(attempt_id, question_id, grader)
    return render_template("grading/_comment_thread.html", comments=comments)
