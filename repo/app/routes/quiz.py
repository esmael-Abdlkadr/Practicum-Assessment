import json
from datetime import datetime, timezone

from flask import Blueprint, Response, abort, jsonify, make_response, redirect, render_template, request, url_for

from app.extensions import db
from app.models.assignment import CohortMember
from app.models.attempt import Attempt, AttemptAnswer
from app.models.grading import GradingComment, GradingResult
from app.models.paper import Paper, PaperQuestion
from app.models.question import Question
from app.services import attempt_service, paper_service
from app.services.decorators import login_required, require_role
from app.services.session_service import get_current_user

quiz_bp = Blueprint("quiz", __name__, url_prefix="/quiz")


def _available_papers_for_student(student_id):
    cohort_ids = [m.cohort_id for m in CohortMember.query.filter_by(user_id=student_id, role_in_cohort="student").all()]
    if not cohort_ids:
        return []
    return (
        Paper.query.filter(Paper.cohort_id.in_(cohort_ids), Paper.status == "published")
        .order_by(Paper.id.desc())
        .all()
    )


def _extract_answers_from_request():
    answers = {}
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        for k, v in payload.items():
            key = str(k)
            if key.startswith("answer_"):
                answers[key.replace("answer_", "", 1)] = v
            else:
                answers[key] = v
    else:
        for key in request.form.keys():
            if not key.startswith("answer_"):
                continue
            qid = key.replace("answer_", "", 1)
            vals = request.form.getlist(key)
            answers[qid] = vals if len(vals) > 1 else (vals[0] if vals else "")
    return answers


@quiz_bp.app_template_filter("format_time")
def format_time(seconds):
    seconds = int(seconds or 0)
    mins = seconds // 60
    secs = seconds % 60
    return f"{mins:02d}:{secs:02d}"


@quiz_bp.get("")
@login_required
@require_role("student")
def quiz_list():
    student = get_current_user()
    papers = _available_papers_for_student(student.id)
    stats = {}
    for p in papers:
        used = Attempt.query.filter_by(paper_id=p.id, student_id=student.id, status="finalized").count()
        stats[p.id] = used
    return render_template("quiz/list.html", papers=papers, stats=stats, now=datetime.now(timezone.utc).replace(tzinfo=None))


@quiz_bp.post("/<int:paper_id>/start")
@login_required
@require_role("student")
def start_quiz(paper_id: int):
    student = get_current_user()
    paper = Paper.query.get_or_404(paper_id)

    if paper.status != "published":
        return "<div class='alert alert-danger' role='alert'>This assessment is not available.</div>", 403

    membership = CohortMember.query.filter_by(
        cohort_id=paper.cohort_id,
        user_id=student.id,
        role_in_cohort="student",
    ).first()
    if not membership:
        return "<div class='alert alert-danger' role='alert'>You are not enrolled in this assessment.</div>", 403

    resumed = attempt_service.get_or_resume_attempt(paper.id, student.id)
    if resumed:
        return redirect(url_for("quiz.take_quiz", paper_id=paper.id))

    attempt, reason = attempt_service.start_attempt(paper, student)
    if attempt:
        return redirect(url_for("quiz.take_quiz", paper_id=paper.id))

    message = "Unable to start attempt."
    status_code = 400
    if reason == "outside_window":
        message = "Paper is outside its availability window."
    elif reason == "no_attempts_remaining":
        message = "No attempts remaining"
    elif reason == "not_published":
        message = "This assessment is not available."
        status_code = 403
    elif reason == "not_enrolled":
        message = "You are not enrolled in this assessment."
        status_code = 403
    return f"<div class='alert alert-danger' role='alert'>{message}</div>", status_code


@quiz_bp.get("/<int:paper_id>/take")
@login_required
@require_role("student")
def take_quiz(paper_id: int):
    student = get_current_user()
    paper = Paper.query.get_or_404(paper_id)
    attempt = attempt_service.get_or_resume_attempt(paper_id, student.id)
    if not attempt:
        return redirect(url_for("quiz.quiz_list"))

    questions = paper_service.get_questions_for_student(paper, student.id)
    saved_answers = {
        a.question_id: a.answer for a in AttemptAnswer.query.filter_by(attempt_id=attempt.id).all()
    }
    time_remaining = attempt_service.get_time_remaining(attempt)
    return render_template(
        "quiz/take.html",
        paper=paper,
        attempt=attempt,
        questions=questions,
        saved_answers=saved_answers,
        time_remaining=time_remaining,
    )


@quiz_bp.post("/<int:paper_id>/autosave")
@login_required
@require_role("student")
def autosave(paper_id: int):
    student = get_current_user()
    attempt = attempt_service.get_or_resume_attempt(paper_id, student.id)
    if not attempt:
        return "<span id='autosave-indicator' class='text-danger'>Save failed</span>", 400

    answers = _extract_answers_from_request()
    ok = attempt_service.autosave_answers(attempt.id, answers, student.id)
    if not ok:
        return "<span id='autosave-indicator' class='text-danger'>Save failed</span>", 400

    stamp = datetime.now(timezone.utc).replace(tzinfo=None).strftime("%H:%M:%S")
    return f"<span id='autosave-indicator'>Saved at {stamp}</span>"


@quiz_bp.post("/<int:paper_id>/submit")
@login_required
@require_role("student")
def submit_quiz(paper_id: int):
    student = get_current_user()
    attempt = (
        Attempt.query.filter_by(paper_id=paper_id, student_id=student.id)
        .order_by(Attempt.id.desc())
        .first()
    )
    if not attempt:
        return "<div id='submit-result' class='alert alert-danger'>No active attempt found.</div>", 400

    token = request.form.get("submission_token") or ""
    answers = _extract_answers_from_request()
    ok, reason = attempt_service.finalize_attempt(attempt.id, answers, token, student.id)
    if ok:
        response = make_response("", 204)
        response.headers["HX-Redirect"] = url_for("quiz.result_page", paper_id=paper_id, attempt_id=attempt.id)
        return response

    if reason == "already_submitted":
        return "<div id='submit-result' class='alert alert-warning'>Your submission was already recorded.</div>"
    if reason == "expired":
        return "<div id='submit-result' class='alert alert-warning'>Time has expired. Your answers have been auto-submitted.</div>"
    return "<div id='submit-result' class='alert alert-danger'>Submission failed.</div>", 400


@quiz_bp.get("/<int:paper_id>/result/<int:attempt_id>")
@login_required
@require_role("student")
def result_page(paper_id: int, attempt_id: int):
    student = get_current_user()
    attempt = Attempt.query.get_or_404(attempt_id)
    if attempt.student_id != student.id or attempt.paper_id != paper_id:
        return abort(403)

    rows = (
        db.session.query(PaperQuestion, Question)
        .join(Question, Question.id == PaperQuestion.question_id)
        .filter(PaperQuestion.paper_id == paper_id)
        .order_by(PaperQuestion.order_index.asc())
        .all()
    )
    ans_map = {a.question_id: a.answer for a in AttemptAnswer.query.filter_by(attempt_id=attempt.id).all()}
    grade_map = {g.question_id: g for g in GradingResult.query.filter_by(attempt_id=attempt.id).all()}
    results = []
    for link, q in rows:
        answer = ans_map.get(q.id)
        grade = grade_map.get(q.id)
        comments = (
            GradingComment.query.filter_by(attempt_id=attempt.id, question_id=q.id, is_internal=False)
            .order_by(GradingComment.created_at.asc())
            .all()
        )
        results.append(
            {
                "question": q,
                "answer": answer,
                "grade": grade,
                "pending": (grade is None) or (grade.status == "pending"),
                "comments": comments,
            }
        )

    return render_template("quiz/result.html", attempt=attempt, paper_id=paper_id, results=results)


@quiz_bp.get("/<int:paper_id>/time-check")
@login_required
@require_role("student")
def time_check(paper_id: int):
    student = get_current_user()
    attempt = attempt_service.get_or_resume_attempt(paper_id, student.id)
    if not attempt:
        return jsonify({"seconds_remaining": 0})
    return jsonify({"seconds_remaining": attempt_service.get_time_remaining(attempt)})
