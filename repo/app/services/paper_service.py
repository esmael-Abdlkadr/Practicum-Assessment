import json
import random
from datetime import datetime, timezone
from types import SimpleNamespace

from app.extensions import db
from app.models.paper import Paper, PaperQuestion
from app.models.question import Question
from app.services import audit_service, question_service


def create_paper(data: dict, creator) -> Paper:
    max_attempts = int(data.get("max_attempts") or 1)
    if max_attempts > 3:
        raise ValueError("Maximum attempts cannot exceed 3.")

    row = Paper(
        title=(data.get("title") or "").strip(),
        description=(data.get("description") or "").strip() or None,
        cohort_id=int(data.get("cohort_id")) if data.get("cohort_id") else None,
        creator_id=creator.id,
        status="draft",
        time_limit_min=int(data.get("time_limit_min") or 45),
        max_attempts=max_attempts,
        available_from=datetime.fromisoformat(data.get("available_from")) if data.get("available_from") else None,
        available_until=datetime.fromisoformat(data.get("available_until")) if data.get("available_until") else None,
        randomize=bool(data.get("randomize")),
        draw_count=int(data.get("draw_count")) if data.get("draw_count") else None,
        draw_tags=data.get("draw_tags"),
        shuffle_options=bool(data.get("shuffle_options", True)),
    )
    db.session.add(row)
    db.session.commit()
    audit_service.log(action="PAPER_CREATED", resource_type="paper", resource_id=row.id)
    return row


def add_question_to_paper(paper_id, question_id, score_points, order_index):
    paper = Paper.query.get_or_404(paper_id)
    if paper.status != "draft":
        raise ValueError("Can only edit draft papers.")
    exists = PaperQuestion.query.filter_by(paper_id=paper_id, question_id=question_id).first()
    if exists:
        return exists
    row = PaperQuestion(
        paper_id=paper_id,
        question_id=question_id,
        score_points=float(score_points),
        order_index=int(order_index),
    )
    db.session.add(row)
    db.session.commit()
    return row


def remove_question_from_paper(paper_id, question_id):
    row = PaperQuestion.query.filter_by(paper_id=paper_id, question_id=question_id).first()
    if row:
        db.session.delete(row)
        db.session.commit()


def reorder_questions(paper_id, ordered_ids: list[int]):
    for idx, qid in enumerate(ordered_ids):
        row = PaperQuestion.query.filter_by(paper_id=paper_id, question_id=int(qid)).first()
        if row:
            row.order_index = idx
            db.session.add(row)
    db.session.commit()


def publish_paper(paper_id, actor):
    paper = Paper.query.get_or_404(paper_id)
    rows = PaperQuestion.query.filter_by(paper_id=paper_id).all()
    if not rows:
        raise ValueError("Paper must contain at least one question.")
    if paper.available_from and paper.available_until and paper.available_from >= paper.available_until:
        raise ValueError("Availability window is invalid.")
    if (paper.max_attempts or 1) > 3:
        raise ValueError("Maximum attempts cannot exceed 3.")

    if paper.randomize:
        tags = json.loads(paper.draw_tags or "[]") if paper.draw_tags else []
        pool = question_service.get_question_pool(tags=tags, school_id=_paper_school_id(paper_id))
        if (paper.draw_count or 0) > len(pool):
            raise ValueError("Draw count exceeds available question pool.")

    paper.status = "published"
    paper.published_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.session.add(paper)
    db.session.commit()
    audit_service.log(action="PAPER_PUBLISHED", resource_type="paper", resource_id=paper.id)
    return paper


def close_paper(paper_id, actor):
    paper = Paper.query.get_or_404(paper_id)
    paper.status = "closed"
    db.session.add(paper)
    db.session.commit()
    audit_service.log(action="PAPER_CLOSED", resource_type="paper", resource_id=paper.id)


def _paper_school_id(paper_id):
    first = (
        db.session.query(Question.school_id)
        .join(PaperQuestion, PaperQuestion.question_id == Question.id)
        .filter(PaperQuestion.paper_id == paper_id)
        .first()
    )
    return first[0] if first else None


def _question_view(q: Question, shuffled_options_json: str | None = None) -> SimpleNamespace:
    """Return a detached, read-only view of a Question for rendering.

    Using SimpleNamespace keeps the interface identical to ORM rows so templates
    can access ``q.id``, ``q.stem``, ``q.question_type``, ``q.options``, etc.,
    but mutations never touch the underlying SQLAlchemy-tracked entity.
    """
    return SimpleNamespace(
        id=q.id,
        stem=q.stem,
        question_type=q.question_type,
        options=shuffled_options_json if shuffled_options_json is not None else q.options,
        tags=q.tags,
        difficulty=q.difficulty,
        explanation=q.explanation,
    )


def get_questions_for_student(paper: Paper, student_id: int):
    seed = int(f"{student_id}{paper.id}")
    rng = random.Random(seed)

    if paper.randomize:
        tags = json.loads(paper.draw_tags or "[]") if paper.draw_tags else []
        pool = question_service.get_question_pool(tags=tags, school_id=_paper_school_id(paper.id))
        draw_count = paper.draw_count or len(pool)
        selected = rng.sample(pool, draw_count)
    else:
        selected = (
            db.session.query(Question)
            .join(PaperQuestion, PaperQuestion.question_id == Question.id)
            .filter(PaperQuestion.paper_id == paper.id)
            .order_by(PaperQuestion.order_index.asc())
            .all()
        )

    views = []
    for q in selected:
        if paper.shuffle_options and q.options:
            opts = json.loads(q.options)
            rng.shuffle(opts)
            views.append(_question_view(q, shuffled_options_json=json.dumps(opts)))
        else:
            views.append(_question_view(q))

    return views


def validate_availability(paper: Paper):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if paper.available_from and now < paper.available_from:
        return False, "Paper is not yet available."
    if paper.available_until and now > paper.available_until:
        return False, "Paper is no longer available."
    if (paper.max_attempts or 1) < 1:
        return False, "Attempt limit is invalid."
    return True, ""
