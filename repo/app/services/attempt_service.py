import secrets
import json
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models.attempt import Attempt, AttemptAnswer
from app.services import audit_service, grading_service


def start_attempt(paper, student):
    if paper.status != "published":
        return None, "not_published"

    from app.models.assignment import CohortMember

    membership = CohortMember.query.filter_by(
        cohort_id=paper.cohort_id,
        user_id=student.id,
        role_in_cohort="student",
    ).first()
    if not membership:
        return None, "not_enrolled"

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if paper.available_from and now < paper.available_from:
        return None, "outside_window"
    if paper.available_until and now > paper.available_until:
        return None, "outside_window"

    finalized_count = Attempt.query.filter_by(paper_id=paper.id, student_id=student.id, status="finalized").count()
    if finalized_count >= (paper.max_attempts or 1):
        return None, "no_attempts_remaining"

    existing = (
        Attempt.query.filter_by(paper_id=paper.id, student_id=student.id, status="in_progress")
        .order_by(Attempt.id.desc())
        .first()
    )
    if existing:
        if existing.expires_at and existing.expires_at <= now:
            existing.status = "timed_out"
            db.session.add(existing)
            db.session.commit()
            grading_service.auto_grade(existing)
        else:
            return existing, "resumed"

    token = secrets.token_hex(32)
    time_limit = int(paper.time_limit_min or 45)
    attempt = Attempt(
        paper_id=paper.id,
        student_id=student.id,
        status="in_progress",
        started_at=now,
        time_limit_min=time_limit,
        expires_at=now + timedelta(minutes=time_limit),
        autosave_count=0,
        submission_token=token,
    )
    db.session.add(attempt)
    db.session.commit()
    audit_service.log(action="ATTEMPT_STARTED", resource_type="attempt", resource_id=attempt.id)
    return attempt, "ok"


def get_or_resume_attempt(paper_id, student_id):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    attempt = (
        Attempt.query.filter_by(paper_id=paper_id, student_id=student_id, status="in_progress")
        .order_by(Attempt.id.desc())
        .first()
    )
    if not attempt:
        return None
    if attempt.expires_at and attempt.expires_at <= now:
        attempt.status = "timed_out"
        db.session.add(attempt)
        db.session.commit()
        grading_service.auto_grade(attempt)
        return None
    return attempt


def autosave_answers(attempt_id, answers: dict, student_id):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    attempt = Attempt.query.get_or_404(attempt_id)
    if attempt.student_id != student_id or attempt.status != "in_progress":
        return False
    if attempt.expires_at and attempt.expires_at <= now:
        attempt.status = "timed_out"
        db.session.add(attempt)
        db.session.commit()
        grading_service.auto_grade(attempt)
        return False

    for qid, answer in (answers or {}).items():
        if qid is None:
            continue
        existing = AttemptAnswer.query.filter_by(attempt_id=attempt.id, question_id=int(qid)).first()
        if not existing:
            existing = AttemptAnswer(attempt_id=attempt.id, question_id=int(qid))
        existing.answer = json.dumps(answer) if isinstance(answer, (list, dict)) else str(answer)
        existing.saved_at = now
        existing.is_autosave = True
        db.session.add(existing)

    attempt.autosave_count = int(attempt.autosave_count or 0) + 1
    db.session.add(attempt)
    db.session.commit()
    audit_service.log(
        action="QUIZ_AUTOSAVE",
        resource_type="attempt",
        resource_id=attempt.id,
        extra={"autosave_count": attempt.autosave_count},
    )
    return True


def finalize_attempt(attempt_id, answers: dict, token: str, student_id):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    attempt = Attempt.query.get_or_404(attempt_id)
    if attempt.student_id != student_id:
        return False, "forbidden"
    if attempt.status in ["finalized", "submitted"]:
        return False, "already_submitted"
    if attempt.status != "in_progress":
        return False, "already_submitted"
    if not attempt.submission_token or token != attempt.submission_token:
        return False, "already_submitted"

    if attempt.expires_at and attempt.expires_at <= now:
        attempt.status = "timed_out"
        db.session.add(attempt)
        db.session.commit()
        grading_service.auto_grade(attempt)
        return False, "expired"

    for qid, answer in (answers or {}).items():
        existing = AttemptAnswer.query.filter_by(attempt_id=attempt.id, question_id=int(qid)).first()
        if not existing:
            existing = AttemptAnswer(attempt_id=attempt.id, question_id=int(qid))
        existing.answer = json.dumps(answer) if isinstance(answer, (list, dict)) else str(answer)
        existing.saved_at = now
        existing.is_autosave = False
        db.session.add(existing)

    attempt.status = "finalized"
    attempt.submitted_at = now
    attempt.finalized_at = now
    attempt.submission_token = None
    db.session.add(attempt)
    db.session.commit()

    grading_service.auto_grade(attempt)
    audit_service.log(action="ATTEMPT_FINALIZED", resource_type="attempt", resource_id=attempt.id)
    return True, "ok"


def get_time_remaining(attempt):
    if not attempt.expires_at:
        return 0
    remaining = int((attempt.expires_at - datetime.now(timezone.utc).replace(tzinfo=None)).total_seconds())
    return max(0, remaining)


def check_expired_attempts():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = Attempt.query.filter(Attempt.status == "in_progress", Attempt.expires_at < now).all()
    for attempt in rows:
        attempt.status = "timed_out"
        db.session.add(attempt)
        db.session.commit()
        grading_service.auto_grade(attempt)
    return len(rows)
