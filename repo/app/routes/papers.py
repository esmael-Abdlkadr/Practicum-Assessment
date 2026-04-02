import json
from datetime import datetime
from flask import jsonify

from flask import Blueprint, abort, redirect, render_template, request, url_for

from app.extensions import db
from app.models.assignment import CohortMember
from app.models.org import Cohort
from app.models.paper import Paper, PaperQuestion
from app.models.question import Question
from app.services import audit_service, paper_service, question_service, rbac_service
from app.services.decorators import login_required, require_role
from app.services.session_service import get_current_user

papers_bp = Blueprint("papers", __name__, url_prefix="/admin/papers")


@papers_bp.get("")
@login_required
@require_role("dept_admin")
def list_papers():
    rows = Paper.query.order_by(Paper.id.desc()).all()
    return render_template("admin/papers/list.html", papers=rows)


@papers_bp.get("/new")
@login_required
@require_role("dept_admin")
def new_paper_form():
    cohorts = Cohort.query.filter(Cohort.is_active.is_(True)).all()
    return render_template("admin/papers/new.html", cohorts=cohorts)


@papers_bp.post("")
@login_required
@require_role("dept_admin")
def create_paper():
    user = get_current_user()
    data = {
        "title": request.form.get("title"),
        "description": request.form.get("description"),
        "cohort_id": request.form.get("cohort_id"),
        "time_limit_min": request.form.get("time_limit_min"),
        "max_attempts": request.form.get("max_attempts"),
        "available_from": request.form.get("available_from"),
        "available_until": request.form.get("available_until"),
        "randomize": request.form.get("randomize") == "on",
        "draw_count": request.form.get("draw_count"),
        "draw_tags": json.dumps([t.strip() for t in (request.form.get("draw_tags") or "").split(",") if t.strip()]),
        "shuffle_options": request.form.get("shuffle_options") != "off",
    }
    try:
        row = paper_service.create_paper(data, user)
    except ValueError as exc:
        return abort(400, str(exc))
    return redirect(url_for("papers.paper_builder", id=row.id))


@papers_bp.get("/<int:id>")
@login_required
@require_role("dept_admin")
def paper_builder(id: int):
    paper = Paper.query.get_or_404(id)
    links = (
        db.session.query(PaperQuestion, Question)
        .join(Question, Question.id == PaperQuestion.question_id)
        .filter(PaperQuestion.paper_id == id)
        .order_by(PaperQuestion.order_index.asc())
        .all()
    )
    user = get_current_user()
    filters = {"school_ids": [s.id for s in rbac_service.get_accessible_schools(user)]}
    bank = question_service.search_questions(filters)
    return render_template("admin/papers/builder.html", paper=paper, links=links, bank=bank)


@papers_bp.post("/<int:id>/questions")
@login_required
@require_role("dept_admin")
def add_paper_question(id: int):
    question_id = int(request.form.get("question_id"))
    score_points = float(request.form.get("score_points") or 1.0)
    order_index = int(request.form.get("order_index") or 0)
    try:
        paper_service.add_question_to_paper(id, question_id, score_points, order_index)
    except ValueError as exc:
        return abort(400, str(exc))
    links = (
        db.session.query(PaperQuestion, Question)
        .join(Question, Question.id == PaperQuestion.question_id)
        .filter(PaperQuestion.paper_id == id)
        .order_by(PaperQuestion.order_index.asc())
        .all()
    )
    audit_service.log(
        action="PAPER_QUESTION_ADDED",
        resource_type="paper",
        resource_id=id,
        extra={"question_id": question_id},
    )
    return render_template("admin/papers/_paper_questions_fragment.html", links=links, paper_id=id)


@papers_bp.delete("/<int:id>/questions/<int:qid>")
@login_required
@require_role("dept_admin")
def remove_paper_question(id: int, qid: int):
    paper_service.remove_question_from_paper(id, qid)
    links = (
        db.session.query(PaperQuestion, Question)
        .join(Question, Question.id == PaperQuestion.question_id)
        .filter(PaperQuestion.paper_id == id)
        .order_by(PaperQuestion.order_index.asc())
        .all()
    )
    audit_service.log(
        action="PAPER_QUESTION_REMOVED",
        resource_type="paper",
        resource_id=id,
        extra={"question_id": qid},
    )
    return render_template("admin/papers/_paper_questions_fragment.html", links=links, paper_id=id)


@papers_bp.put("/<int:id>/questions/reorder")
@login_required
@require_role("dept_admin")
def reorder_paper_questions(id: int):
    ordered_ids = request.get_json(force=True).get("ordered_ids", [])
    paper_service.reorder_questions(id, ordered_ids)
    return ""


@papers_bp.post("/<int:id>/publish")
@login_required
@require_role("dept_admin")
def publish_paper(id: int):
    user = get_current_user()
    paper = Paper.query.get_or_404(id)
    paper.time_limit_min = int(request.form.get("time_limit_min") or paper.time_limit_min or 45)
    paper.max_attempts = int(request.form.get("max_attempts") or paper.max_attempts or 1)
    if request.form.get("available_from"):
        try:
            paper.available_from = datetime.fromisoformat(request.form.get("available_from", ""))
        except (ValueError, TypeError):
            return "<div class='alert alert-danger'>Invalid 'Available From' date.</div>", 400
    if request.form.get("available_until"):
        try:
            paper.available_until = datetime.fromisoformat(request.form.get("available_until", ""))
        except (ValueError, TypeError):
            return "<div class='alert alert-danger'>Invalid 'Available Until' date.</div>", 400
    paper.randomize = request.form.get("randomize") == "on"
    paper.draw_count = int(request.form.get("draw_count")) if request.form.get("draw_count") else paper.draw_count
    draw_tags = request.form.get("draw_tags")
    if draw_tags is not None:
        paper.draw_tags = json.dumps([t.strip() for t in draw_tags.split(",") if t.strip()])
    paper.shuffle_options = request.form.get("shuffle_options") != "off"
    db.session.add(paper)
    db.session.commit()

    try:
        paper_service.publish_paper(id, user)
    except ValueError as exc:
        return f"<div class='alert alert-danger' role='alert'>{str(exc)}</div>", 400
    return "<div class='alert alert-success' role='alert'>Paper published.</div>"


@papers_bp.post("/<int:id>/close")
@login_required
@require_role("dept_admin")
def close_paper(id: int):
    user = get_current_user()
    paper_service.close_paper(id, user)
    return "<div class='alert alert-success' role='alert'>Paper closed.</div>"


@papers_bp.get("/student/available")
@login_required
def student_available_papers():
    user = get_current_user()
    if not user or user.role != "student":
        return abort(403)

    cohort_ids = [m.cohort_id for m in CohortMember.query.filter_by(user_id=user.id, role_in_cohort="student").all()]
    papers = (
        Paper.query.filter(Paper.cohort_id.in_(cohort_ids), Paper.status == "published")
        .order_by(Paper.id.desc())
        .all()
    )
    return jsonify(
        [
            {
                "id": p.id,
                "title": p.title,
                "cohort_id": p.cohort_id,
                "status": p.status,
            }
            for p in papers
        ]
    )
