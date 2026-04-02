import json
from datetime import datetime, timezone

from app.extensions import db
from app.models.assignment import CohortMember
from app.models.attempt import Attempt, AttemptAnswer
from app.models.grading import GradingComment, GradingResult
from app.models.paper import Paper, PaperQuestion
from app.models.question import Question
from app.services import audit_service, rbac_service


def _decode(value):
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return value


def _upsert_result(attempt_id, question_id):
    row = GradingResult.query.filter_by(attempt_id=attempt_id, question_id=question_id).first()
    if not row:
        row = GradingResult(attempt_id=attempt_id, question_id=question_id)
    return row


def auto_grade(attempt: Attempt):
    links = (
        db.session.query(PaperQuestion, Question)
        .join(Question, Question.id == PaperQuestion.question_id)
        .filter(PaperQuestion.paper_id == attempt.paper_id)
        .all()
    )
    answers = {a.question_id: a for a in AttemptAnswer.query.filter_by(attempt_id=attempt.id).all()}

    scored = 0.0
    for link, q in links:
        points = float(link.score_points or q.score_points or 0)
        ans = answers.get(q.id)
        student_answer = _decode(ans.answer) if ans else None
        correct_answer = _decode(q.correct_answer)

        result = _upsert_result(attempt.id, q.id)
        result.max_score = points
        result.graded_by = None
        result.graded_at = datetime.now(timezone.utc).replace(tzinfo=None)

        if q.question_type == "single_choice":
            is_correct = str(student_answer or "").strip() == str(correct_answer or "").strip()
            result.is_correct = is_correct
            result.score_awarded = points if is_correct else 0.0
            result.status = "auto_graded"
        elif q.question_type == "multiple_choice":
            user_list = sorted(student_answer or []) if isinstance(student_answer, list) else []
            corr_list = sorted(correct_answer or []) if isinstance(correct_answer, list) else []
            is_correct = user_list == corr_list
            result.is_correct = is_correct
            result.score_awarded = points if is_correct else 0.0
            result.status = "auto_graded"
        elif q.question_type == "true_false":
            is_correct = str(student_answer or "").strip().lower() == str(correct_answer or "").strip().lower()
            result.is_correct = is_correct
            result.score_awarded = points if is_correct else 0.0
            result.status = "auto_graded"
        elif q.question_type == "fill_in":
            is_correct = str(student_answer or "").strip().lower() == str(correct_answer or "").strip().lower()
            result.is_correct = is_correct
            result.score_awarded = points if is_correct else 0.0
            result.status = "auto_graded"
        else:
            result.is_correct = None
            result.score_awarded = 0.0
            result.status = "pending"

        scored += float(result.score_awarded or 0.0)
        db.session.add(result)

    attempt.score = scored
    db.session.add(attempt)
    db.session.commit()
    audit_service.log(action="ATTEMPT_AUTO_GRADED", resource_type="attempt", resource_id=attempt.id)
    return scored


def get_pending_grading(grader, effective_role: str | None = None):
    cohort_ids = [c.id for c in rbac_service.get_accessible_cohorts(grader, effective_role=effective_role)]
    if not cohort_ids:
        return []

    rows = (
        db.session.query(Attempt, Paper)
        .join(Paper, Paper.id == Attempt.paper_id)
        .filter(Paper.cohort_id.in_(cohort_ids))
        .all()
    )

    grouped = []
    for attempt, paper in rows:
        pending_count = GradingResult.query.filter_by(attempt_id=attempt.id, status="pending").count()
        if pending_count <= 0:
            continue
        grouped.append(
            {
                "attempt": attempt,
                "paper": paper,
                "pending_count": pending_count,
            }
        )
    return grouped


def grade_answer(attempt_id, question_id, score, grader, effective_role: str | None = None):
    attempt = Attempt.query.get_or_404(attempt_id)
    paper = Paper.query.get_or_404(attempt.paper_id)
    if not rbac_service.can_access_cohort(grader, paper.cohort_id, effective_role=effective_role):
        raise PermissionError("forbidden")

    link = PaperQuestion.query.filter_by(paper_id=paper.id, question_id=question_id).first()
    if not link:
        raise ValueError("Question not in paper")
    question = Question.query.get_or_404(question_id)
    max_score = float(link.score_points or question.score_points or 0)
    score_val = float(score)
    if score_val > max_score:
        raise ValueError("Score exceeds max score.")

    result = _upsert_result(attempt.id, question_id)
    result.max_score = max_score
    result.score_awarded = score_val
    result.graded_by = grader.id
    result.graded_at = datetime.now(timezone.utc).replace(tzinfo=None)
    result.status = "manually_graded"
    result.is_correct = None
    db.session.add(result)
    db.session.commit()

    remaining = GradingResult.query.filter_by(attempt_id=attempt.id, status="pending").count()
    if remaining == 0:
        attempt.score = calculate_total_score(attempt)
        attempt.status = "finalized"
        db.session.add(attempt)
        db.session.commit()

    audit_service.log(
        action="ANSWER_MANUALLY_GRADED",
        resource_type="grading_result",
        resource_id=result.id,
        extra={"attempt_id": attempt.id, "question_id": question_id, "score": score_val},
    )
    return result


def add_comment(attempt_id, question_id, text, author, is_internal, parent_id=None):
    if parent_id is not None:
        parent = db.session.get(GradingComment, parent_id)
        if parent is None or parent.attempt_id != attempt_id or parent.question_id != question_id:
            raise ValueError("Invalid parent comment")

    row = GradingComment(
        attempt_id=attempt_id,
        question_id=question_id,
        author_id=author.id,
        comment_text=text,
        is_internal=bool(is_internal),
        parent_id=parent_id,
    )
    db.session.add(row)
    db.session.commit()
    audit_service.log(
        action="GRADING_COMMENT_ADDED",
        resource_type="grading_comment",
        resource_id=row.id,
        extra={
            "attempt_id": attempt_id,
            "question_id": question_id,
            "is_internal": bool(is_internal),
            "parent_id": parent_id,
        },
    )
    return row


def get_comments(attempt_id, question_id, viewer):
    query = GradingComment.query.filter_by(
        attempt_id=attempt_id,
        question_id=question_id,
        parent_id=None,
    )
    if viewer.role == "student":
        query = query.filter(GradingComment.is_internal.is_(False))
    return query.order_by(GradingComment.created_at.asc()).all()


def calculate_total_score(attempt):
    rows = GradingResult.query.filter_by(attempt_id=attempt.id).all()
    return float(sum(float(r.score_awarded or 0.0) for r in rows))
