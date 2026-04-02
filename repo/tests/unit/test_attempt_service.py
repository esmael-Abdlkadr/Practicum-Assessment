from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models.attempt import Attempt
from app.models.paper import Paper
from app.models.user import User
from app.services import attempt_service


def test_start_attempt_within_window_creates_attempt(app, seeded_assessment):
    with app.app_context():
        student = User.query.filter_by(username="student1").first()
        paper = db.session.get(Paper, seeded_assessment["paper_id"])
        attempt, reason = attempt_service.start_attempt(paper, student)
        assert attempt is not None
        assert reason in {"ok", "resumed"}


def test_start_attempt_outside_window_error(app, seeded_assessment):
    with app.app_context():
        student = User.query.filter_by(username="student1").first()
        paper = db.session.get(Paper, seeded_assessment["paper_id"])
        paper.available_from = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
        paper.available_until = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=2)
        db.session.add(paper)
        db.session.commit()
        attempt, reason = attempt_service.start_attempt(paper, student)
        assert attempt is None
        assert reason == "outside_window"


def test_start_attempt_when_max_attempts_reached(app, seeded_assessment):
    with app.app_context():
        student = User.query.filter_by(username="student1").first()
        paper = db.session.get(Paper, seeded_assessment["paper_id"])
        paper.max_attempts = 1
        db.session.add(paper)
        db.session.commit()

        db.session.add(
            Attempt(
                paper_id=paper.id,
                student_id=student.id,
                status="finalized",
                started_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=40),
                finalized_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=20),
                time_limit_min=paper.time_limit_min,
                expires_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=10),
                submission_token=None,
            )
        )
        db.session.commit()

        attempt, reason = attempt_service.start_attempt(paper, student)
        assert attempt is None
        assert reason == "no_attempts_remaining"


def test_finalize_attempt_valid_token_sets_finalized_and_clears_token(app, seeded_assessment):
    with app.app_context():
        student = User.query.filter_by(username="student1").first()
        paper = db.session.get(Paper, seeded_assessment["paper_id"])
        attempt, _ = attempt_service.start_attempt(paper, student)
        token = attempt.submission_token
        ok, reason = attempt_service.finalize_attempt(attempt.id, {}, token, student.id)
        attempt = db.session.get(Attempt, attempt.id)
        assert ok is True
        assert reason == "ok"
        assert attempt.status == "finalized"
        assert attempt.submission_token is None


def test_finalize_attempt_used_token_returns_already_submitted(app, seeded_assessment):
    with app.app_context():
        student = User.query.filter_by(username="student1").first()
        paper = db.session.get(Paper, seeded_assessment["paper_id"])
        attempt, _ = attempt_service.start_attempt(paper, student)
        token = attempt.submission_token
        attempt_service.finalize_attempt(attempt.id, {}, token, student.id)
        ok, reason = attempt_service.finalize_attempt(attempt.id, {}, token, student.id)
        assert ok is False
        assert reason == "already_submitted"


def test_get_time_remaining_returns_seconds(app, seeded_assessment):
    with app.app_context():
        student = User.query.filter_by(username="student1").first()
        paper = db.session.get(Paper, seeded_assessment["paper_id"])
        attempt, _ = attempt_service.start_attempt(paper, student)
        remaining = attempt_service.get_time_remaining(attempt)
        assert remaining > 0


def test_check_expired_attempts_marks_timed_out(app, seeded_assessment):
    with app.app_context():
        student = User.query.filter_by(username="student1").first()
        paper = db.session.get(Paper, seeded_assessment["paper_id"])
        attempt = Attempt(
            paper_id=paper.id,
            student_id=student.id,
            status="in_progress",
            started_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=30),
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1),
            time_limit_min=1,
            submission_token="x" * 64,
        )
        db.session.add(attempt)
        db.session.commit()
        changed = attempt_service.check_expired_attempts()
        assert changed >= 1
        assert db.session.get(Attempt, attempt.id).status == "timed_out"
