import json

import pytest

from app.extensions import db
from app.models.attempt import Attempt, AttemptAnswer
from app.models.grading import GradingResult
from app.models.paper import PaperQuestion
from app.models.paper import Paper
from app.models.question import Question
from app.models.user import User
from app.services import grading_service


def _build_attempt(app, seeded_assessment):
    with app.app_context():
        student = User.query.filter_by(username="student1").first()
        paper = db.session.get(Paper, seeded_assessment["paper_id"])
        attempt = Attempt(paper_id=paper.id, student_id=student.id, status="in_progress", time_limit_min=45)
        db.session.add(attempt)
        db.session.flush()

        qids = seeded_assessment["question_ids"]
        q1, q2, q3, q4, q5 = [db.session.get(Question, qid) for qid in qids]
        db.session.add_all(
            [
                AttemptAnswer(attempt_id=attempt.id, question_id=q1.id, answer="A", is_autosave=False),
                AttemptAnswer(attempt_id=attempt.id, question_id=q2.id, answer=json.dumps(["A"]), is_autosave=False),
                AttemptAnswer(attempt_id=attempt.id, question_id=q3.id, answer="true", is_autosave=False),
                AttemptAnswer(attempt_id=attempt.id, question_id=q4.id, answer=" HELLO ", is_autosave=False),
                AttemptAnswer(attempt_id=attempt.id, question_id=q5.id, answer="Essay", is_autosave=False),
            ]
        )
        db.session.commit()
        return attempt.id, q5.id


def test_auto_grade_single_choice_correct(app, seeded_assessment):
    attempt_id, _ = _build_attempt(app, seeded_assessment)
    with app.app_context():
        attempt = db.session.get(Attempt, attempt_id)
        grading_service.auto_grade(attempt)
        q1 = db.session.get(Question, seeded_assessment["question_ids"][0])
        row = GradingResult.query.filter_by(attempt_id=attempt.id, question_id=q1.id).first()
        assert row.status == "auto_graded"
        assert row.score_awarded > 0


def test_auto_grade_multiple_choice_partial_zero(app, seeded_assessment):
    attempt_id, _ = _build_attempt(app, seeded_assessment)
    with app.app_context():
        attempt = db.session.get(Attempt, attempt_id)
        grading_service.auto_grade(attempt)
        q2 = db.session.get(Question, seeded_assessment["question_ids"][1])
        row = GradingResult.query.filter_by(attempt_id=attempt.id, question_id=q2.id).first()
        assert row.score_awarded == 0


def test_auto_grade_true_false_correct(app, seeded_assessment):
    """true_false question graded correctly when answer matches."""
    with app.app_context():
        from app.models.user import User
        student = User.query.filter_by(username="student1").first()
        paper_id = seeded_assessment["paper_id"]
        q3_id = seeded_assessment["question_ids"][2]  # true_false question

        attempt = Attempt(paper_id=paper_id, student_id=student.id, status="in_progress", time_limit_min=45)
        db.session.add(attempt)
        db.session.flush()
        db.session.add(AttemptAnswer(attempt_id=attempt.id, question_id=q3_id, answer="True", is_autosave=False))
        db.session.commit()

        grading_service.auto_grade(attempt)
        row = GradingResult.query.filter_by(attempt_id=attempt.id, question_id=q3_id).first()
        assert row.is_correct is True
        assert row.status == "auto_graded"


def test_auto_grade_true_false_incorrect(app, seeded_assessment):
    """true_false question graded incorrect when answer does not match."""
    with app.app_context():
        from app.models.user import User
        student = User.query.filter_by(username="student1").first()
        paper_id = seeded_assessment["paper_id"]
        q3_id = seeded_assessment["question_ids"][2]  # true_false question

        attempt = Attempt(paper_id=paper_id, student_id=student.id, status="in_progress", time_limit_min=45)
        db.session.add(attempt)
        db.session.flush()
        db.session.add(AttemptAnswer(attempt_id=attempt.id, question_id=q3_id, answer="False", is_autosave=False))
        db.session.commit()

        grading_service.auto_grade(attempt)
        row = GradingResult.query.filter_by(attempt_id=attempt.id, question_id=q3_id).first()
        assert row.is_correct is False
        assert row.status == "auto_graded"


def test_auto_grade_fill_in_case_insensitive(app, seeded_assessment):
    attempt_id, _ = _build_attempt(app, seeded_assessment)
    with app.app_context():
        attempt = db.session.get(Attempt, attempt_id)
        grading_service.auto_grade(attempt)
        q4 = db.session.get(Question, seeded_assessment["question_ids"][3])
        row = GradingResult.query.filter_by(attempt_id=attempt.id, question_id=q4.id).first()
        assert row.is_correct is True


def test_auto_grade_short_answer_pending(app, seeded_assessment):
    attempt_id, q5id = _build_attempt(app, seeded_assessment)
    with app.app_context():
        attempt = db.session.get(Attempt, attempt_id)
        grading_service.auto_grade(attempt)
        row = GradingResult.query.filter_by(attempt_id=attempt.id, question_id=q5id).first()
        assert row.status == "pending"


def test_grade_answer_manual_score_over_max_error(app, seeded_assessment):
    attempt_id, q5id = _build_attempt(app, seeded_assessment)
    with app.app_context():
        attempt = db.session.get(Attempt, attempt_id)
        attempt.status = "in_progress"
        db.session.add(attempt)
        db.session.commit()
        grader = User.query.filter_by(username="advisor1").first()
        with pytest.raises(ValueError):
            grading_service.grade_answer(attempt.id, q5id, 999, grader)


def test_calculate_total_score_correct_sum(app, seeded_assessment):
    attempt_id, q5id = _build_attempt(app, seeded_assessment)
    with app.app_context():
        attempt = db.session.get(Attempt, attempt_id)
        grading_service.auto_grade(attempt)
        grader = User.query.filter_by(username="advisor1").first()
        grading_service.grade_answer(attempt.id, q5id, 4, grader)
        total = grading_service.calculate_total_score(attempt)
        assert total >= 4


def test_add_and_get_comments_visibility(app, seeded_assessment):
    attempt_id, q5id = _build_attempt(app, seeded_assessment)
    with app.app_context():
        grader = User.query.filter_by(username="advisor1").first()
        student = User.query.filter_by(username="student1").first()
        grading_service.add_comment(attempt_id, q5id, "public", grader, False)
        grading_service.add_comment(attempt_id, q5id, "internal", grader, True)

        student_view = grading_service.get_comments(attempt_id, q5id, student)
        grader_view = grading_service.get_comments(attempt_id, q5id, grader)
        assert len(student_view) == 1
        assert len(grader_view) == 2


def test_add_reply_comment_links_to_parent(app, seeded_assessment):
    """A reply must have parent_id pointing to the parent comment."""
    attempt_id, q5id = _build_attempt(app, seeded_assessment)
    with app.app_context():
        grader = User.query.filter_by(username="advisor1").first()
        parent = grading_service.add_comment(attempt_id, q5id, "parent", grader, False)
        reply = grading_service.add_comment(attempt_id, q5id, "reply", grader, False, parent_id=parent.id)
        assert reply.parent_id == parent.id


def test_get_comments_returns_only_top_level(app, seeded_assessment):
    """get_comments must return only root comments; replies are accessed via relationship."""
    attempt_id, q5id = _build_attempt(app, seeded_assessment)
    with app.app_context():
        grader = User.query.filter_by(username="advisor1").first()
        parent = grading_service.add_comment(attempt_id, q5id, "root", grader, False)
        grading_service.add_comment(attempt_id, q5id, "reply", grader, False, parent_id=parent.id)
        top_level = grading_service.get_comments(attempt_id, q5id, grader)
        assert len(top_level) == 1
        assert top_level[0].id == parent.id


def test_add_comment_invalid_parent_raises(app, seeded_assessment):
    """add_comment with a non-existent parent_id must raise ValueError."""
    attempt_id, q5id = _build_attempt(app, seeded_assessment)
    with app.app_context():
        grader = User.query.filter_by(username="advisor1").first()
        with pytest.raises(ValueError):
            grading_service.add_comment(attempt_id, q5id, "bad", grader, False, parent_id=99999)
