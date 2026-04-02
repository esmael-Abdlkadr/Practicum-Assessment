import json

from flask import Blueprint, abort, render_template, request

from app.extensions import db
from app.models.grading import Rubric
from app.models.question import Question
from app.services import audit_service, question_service, rbac_service
from app.services.decorators import login_required, require_role
from app.services.session_service import get_current_user

questions_bp = Blueprint("questions", __name__, url_prefix="/admin/questions")


def _parse_question_payload(form):
    qtype = (form.get("question_type") or "").strip()
    options_text = (form.get("options_text") or "").strip()
    correct_text = (form.get("correct_answer") or "").strip()
    tags_text = (form.get("tags_text") or "").strip()

    options = None
    correct_answer = None
    if qtype in {"single_choice", "multiple_choice", "true_false"}:
        if qtype == "true_false":
            options = [{"key": "True", "text": "True"}, {"key": "False", "text": "False"}]
        else:
            options = []
            for idx, part in enumerate([p.strip() for p in options_text.split("|") if p.strip()]):
                key = chr(ord("A") + idx)
                options.append({"key": key, "text": part})
        if qtype == "multiple_choice":
            correct_answer = json.dumps([x.strip() for x in correct_text.split(",") if x.strip()])
        else:
            correct_answer = correct_text
    elif qtype == "fill_in":
        correct_answer = correct_text
    elif qtype == "short_answer":
        correct_answer = None

    tags = json.dumps([t.strip() for t in tags_text.split(",") if t.strip()])

    school_id = form.get("school_id")
    return {
        "school_id": int(school_id) if school_id else None,
        "question_type": qtype,
        "stem": (form.get("stem") or "").strip(),
        "options": json.dumps(options) if options is not None else None,
        "correct_answer": correct_answer,
        "explanation": (form.get("explanation") or "").strip() or None,
        "tags": tags,
        "difficulty": (form.get("difficulty") or "medium").strip(),
        "score_points": float(form.get("score_points") or 1.0),
    }


def _question_filters(user):
    schools = rbac_service.get_accessible_schools(user)
    school_ids = [s.id for s in schools]
    return {
        "question_type": request.args.get("question_type", "") or request.form.get("question_type", ""),
        "difficulty": request.args.get("difficulty", "") or request.form.get("difficulty", ""),
        "tag": request.args.get("tag", "") or request.form.get("tag", ""),
        "search": request.args.get("search", "") or request.form.get("search", ""),
        "school_ids": school_ids,
    }


@questions_bp.get("")
@login_required
@require_role("dept_admin")
def list_questions():
    user = get_current_user()
    filters = _question_filters(user)
    questions = question_service.search_questions(filters)
    schools = rbac_service.get_accessible_schools(user)
    return render_template("admin/questions/list.html", questions=questions, filters=filters, schools=schools)


@questions_bp.post("")
@login_required
@require_role("dept_admin")
def create_question():
    user = get_current_user()
    data = _parse_question_payload(request.form)
    try:
        question_service.create_question(data, user)
    except ValueError as exc:
        filters = _question_filters(user)
        questions = question_service.search_questions(filters)
        schools = rbac_service.get_accessible_schools(user)
        return render_template("admin/questions/_list_fragment.html", questions=questions, filters=filters, schools=schools, error_message=str(exc))

    filters = _question_filters(user)
    questions = question_service.search_questions(filters)
    schools = rbac_service.get_accessible_schools(user)
    return render_template("admin/questions/_list_fragment.html", questions=questions, filters=filters, schools=schools)


@questions_bp.get("/<int:id>/edit")
@login_required
@require_role("dept_admin")
def edit_question_form(id: int):
    row = Question.query.get_or_404(id)
    user = get_current_user()
    schools = rbac_service.get_accessible_schools(user)
    return render_template("admin/questions/_form.html", question=row, schools=schools)


@questions_bp.put("/<int:id>")
@login_required
@require_role("dept_admin")
def update_question(id: int):
    user = get_current_user()
    data = _parse_question_payload(request.form)
    try:
        question_service.update_question(id, data, user)
    except ValueError as exc:
        return abort(400, str(exc))

    filters = _question_filters(user)
    questions = question_service.search_questions(filters)
    schools = rbac_service.get_accessible_schools(user)
    return render_template("admin/questions/_list_fragment.html", questions=questions, filters=filters, schools=schools)


@questions_bp.delete("/<int:id>")
@login_required
@require_role("dept_admin")
def delete_question(id: int):
    user = get_current_user()
    question_service.soft_delete_question(id, user)
    filters = _question_filters(user)
    questions = question_service.search_questions(filters)
    schools = rbac_service.get_accessible_schools(user)
    return render_template("admin/questions/_list_fragment.html", questions=questions, filters=filters, schools=schools)


@questions_bp.get("/<int:id>/rubric")
@login_required
@require_role("dept_admin")
def rubric_editor(id: int):
    question = Question.query.get_or_404(id)
    rubric = Rubric.query.filter_by(question_id=id).first()
    return render_template("admin/questions/_rubric_editor.html", question=question, rubric=rubric, success_message="")


@questions_bp.post("/<int:id>/rubric")
@login_required
@require_role("dept_admin")
def save_rubric(id: int):
    question = Question.query.get_or_404(id)
    criteria = (request.form.get("criteria") or "").strip()
    if not criteria:
        return abort(400)

    row = Rubric.query.filter_by(question_id=id).first()
    if not row:
        row = Rubric(question_id=id, criteria=criteria)
    else:
        row.criteria = criteria
    db.session.add(row)
    db.session.commit()
    audit_service.log(
        action="RUBRIC_SAVED",
        resource_type="question",
        resource_id=id,
        new_value={"criteria": criteria},
    )
    return render_template("admin/questions/_rubric_editor.html", question=question, rubric=row, success_message="Rubric saved.")
