import json
from datetime import datetime

from app.extensions import db
from app.models.question import Question
from app.services import audit_service

VALID_TYPES = {"single_choice", "multiple_choice", "true_false", "fill_in", "short_answer"}


def _loads_list(raw):
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    try:
        val = json.loads(raw)
        return val if isinstance(val, list) else []
    except json.JSONDecodeError:
        return []


def validate_question(data: dict) -> tuple[bool, str]:
    qtype = data.get("question_type")
    options = _loads_list(data.get("options"))
    correct = data.get("correct_answer")

    if qtype not in VALID_TYPES:
        return False, f"Invalid question type: {qtype}"

    if qtype in {"single_choice", "multiple_choice"} and not options:
        return False, "Choice questions require options."

    if qtype == "single_choice":
        if not (2 <= len(options) <= 6):
            return False, "Single choice requires 2-6 options."
        if not isinstance(correct, str):
            return False, "Single choice requires one correct answer key."
        if "," in correct:
            return False, "Single choice requires one correct answer key."
        keys = [o.get("key") for o in options if isinstance(o, dict)]
        if correct not in keys:
            return False, "Single choice correct answer must match an option key."
    elif qtype == "multiple_choice":
        if not (2 <= len(options) <= 6):
            return False, "Multiple choice requires 2-6 options."
        answers = _loads_list(correct)
        if len(answers) < 2:
            return False, "Multiple choice requires at least 2 correct answers."
        keys = [o.get("key") for o in options if isinstance(o, dict)]
        if any(ans not in keys for ans in answers):
            return False, "Multiple choice correct answers must match option keys."
    elif qtype == "true_false":
        keys = [o.get("key") for o in options if isinstance(o, dict)]
        if keys != ["True", "False"]:
            return False, "True/False options must be exactly True and False."
        if correct not in ["True", "False"]:
            return False, "True/False must have one correct answer."
    elif qtype == "fill_in":
        if correct is None or not isinstance(correct, str) or not correct.strip():
            return False, "Fill-in requires a string correct answer."
    elif qtype == "short_answer":
        if correct not in [None, "", "null"]:
            return False, "Short answer correct_answer must be null."

    return True, ""


def _to_storage_value(value):
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return value


def create_question(data: dict | None = None, creator=None, **kwargs) -> Question:
    if data is None:
        data = {
            "creator_id": kwargs.get("creator_id"),
            "school_id": kwargs.get("school_id"),
            "question_type": kwargs.get("question_type"),
            "stem": kwargs.get("stem"),
            "options": kwargs.get("options"),
            "correct_answer": kwargs.get("correct_answer"),
            "explanation": kwargs.get("explanation"),
            "tags": kwargs.get("tags"),
            "difficulty": kwargs.get("difficulty", "medium"),
            "score_points": kwargs.get("score_points", 1.0),
        }

    ok, error = validate_question(data)
    if not ok:
        raise ValueError(error)

    creator_id = None
    if creator is not None:
        creator_id = creator.id
    elif data.get("creator_id") is not None:
        creator_id = int(data.get("creator_id"))
    else:
        raise ValueError("creator_id is required")

    row = Question(
        creator_id=creator_id,
        school_id=data.get("school_id"),
        question_type=data.get("question_type"),
        stem=data.get("stem", "").strip(),
        options=_to_storage_value(data.get("options")),
        correct_answer=_to_storage_value(data.get("correct_answer")),
        explanation=data.get("explanation"),
        tags=_to_storage_value(data.get("tags")),
        difficulty=data.get("difficulty", "medium"),
        score_points=float(data.get("score_points") or 1.0),
        is_active=True,
    )
    db.session.add(row)
    db.session.commit()
    audit_service.log(action="QUESTION_CREATED", resource_type="question", resource_id=row.id)
    return row


def update_question(question_id, data: dict, editor):
    row = Question.query.get_or_404(question_id)
    old = {
        "stem": row.stem,
        "question_type": row.question_type,
        "options": row.options,
        "correct_answer": row.correct_answer,
        "difficulty": row.difficulty,
    }
    merged = {
        "question_type": data.get("question_type", row.question_type),
        "options": data.get("options", row.options),
        "correct_answer": data.get("correct_answer", row.correct_answer),
    }
    ok, error = validate_question(merged)
    if not ok:
        raise ValueError(error)

    row.question_type = data.get("question_type", row.question_type)
    row.stem = data.get("stem", row.stem)
    row.options = data.get("options", row.options)
    row.correct_answer = data.get("correct_answer", row.correct_answer)
    row.explanation = data.get("explanation", row.explanation)
    row.tags = data.get("tags", row.tags)
    row.difficulty = data.get("difficulty", row.difficulty)
    row.score_points = float(data.get("score_points", row.score_points or 1.0))
    if data.get("school_id") is not None:
        row.school_id = data.get("school_id")

    db.session.add(row)
    db.session.commit()
    audit_service.log(
        action="QUESTION_UPDATED",
        resource_type="question",
        resource_id=row.id,
        old_value=old,
        new_value={"stem": row.stem, "question_type": row.question_type},
    )
    return row


def soft_delete_question(question_id, actor):
    row = Question.query.get_or_404(question_id)
    row.soft_delete()
    db.session.add(row)
    db.session.commit()
    audit_service.log(action="QUESTION_SOFT_DELETED", resource_type="question", resource_id=row.id)


def search_questions(filters: dict):
    query = Question.query.filter(Question.is_active.is_(True), Question.deleted_at.is_(None))

    qtype = (filters.get("question_type") or "").strip()
    difficulty = (filters.get("difficulty") or "").strip()
    tag = (filters.get("tag") or "").strip()
    search_text = (filters.get("search") or "").strip()
    school_id = filters.get("school_id")
    school_ids = filters.get("school_ids")

    if qtype:
        query = query.filter(Question.question_type == qtype)
    if difficulty:
        query = query.filter(Question.difficulty == difficulty)
    if tag:
        query = query.filter(Question.tags.like(f"%{tag}%"))
    if search_text:
        query = query.filter(Question.stem.ilike(f"%{search_text}%"))
    if school_id:
        query = query.filter(Question.school_id == int(school_id))
    if school_ids:
        query = query.filter(Question.school_id.in_(school_ids))

    return query.order_by(Question.id.desc()).all()


def get_question_pool(tags: list, school_id: int):
    query = Question.query.filter(
        Question.is_active.is_(True),
        Question.deleted_at.is_(None),
        Question.school_id == school_id,
    )
    for tag in tags or []:
        query = query.filter(Question.tags.like(f"%{tag}%"))
    return query.all()
