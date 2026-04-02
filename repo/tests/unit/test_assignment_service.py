from app.extensions import db
from app.models.assignment import AssignmentSubmission
from app.models.user import User
from app.services import assignment_service


def test_submit_empty_content_raises_value_error(app, seeded_assignment):
    """Submitting empty content must raise ValueError."""
    with app.app_context():
        student = db.session.get(User, seeded_assignment["student_id"])
        submission = AssignmentSubmission.query.filter_by(
            assignment_id=seeded_assignment["assignment_id"],
            student_id=student.id,
        ).first()
        submission.content = ""
        db.session.add(submission)
        db.session.commit()

        try:
            assignment_service.submit(submission.id, student)
            assert False, "Expected ValueError"
        except ValueError:
            assert True


def test_submit_already_submitted_raises_value_error(app, seeded_assignment):
    """Submitting twice must raise ValueError."""
    with app.app_context():
        student = db.session.get(User, seeded_assignment["student_id"])
        submission = AssignmentSubmission.query.filter_by(
            assignment_id=seeded_assignment["assignment_id"],
            student_id=student.id,
        ).first()
        submission.content = "Answer"
        db.session.add(submission)
        db.session.commit()

        assignment_service.submit(submission.id, student)
        try:
            assignment_service.submit(submission.id, student)
            assert False, "Expected ValueError"
        except ValueError:
            assert True


def test_grade_score_exceeds_max_raises_value_error(app, seeded_assignment):
    """Score > max_score must raise ValueError."""
    with app.app_context():
        student = db.session.get(User, seeded_assignment["student_id"])
        advisor = db.session.get(User, seeded_assignment["advisor_id"])
        submission = AssignmentSubmission.query.filter_by(
            assignment_id=seeded_assignment["assignment_id"],
            student_id=student.id,
        ).first()
        submission.content = "Answer"
        db.session.add(submission)
        db.session.commit()
        assignment_service.submit(submission.id, student)

        try:
            assignment_service.grade_submission(submission.id, 101.0, "too high", advisor)
            assert False, "Expected ValueError"
        except ValueError:
            assert True


def test_grade_negative_score_raises_value_error(app, seeded_assignment):
    """Negative score must raise ValueError."""
    with app.app_context():
        student = db.session.get(User, seeded_assignment["student_id"])
        advisor = db.session.get(User, seeded_assignment["advisor_id"])
        submission = AssignmentSubmission.query.filter_by(
            assignment_id=seeded_assignment["assignment_id"],
            student_id=student.id,
        ).first()
        submission.content = "Answer"
        db.session.add(submission)
        db.session.commit()
        assignment_service.submit(submission.id, student)

        try:
            assignment_service.grade_submission(submission.id, -1.0, "negative", advisor)
            assert False, "Expected ValueError"
        except ValueError:
            assert True


def test_student_cannot_access_other_cohort_assignment(app, seeded_assignment):
    """get_assignment_for_student must raise PermissionError if student not in cohort."""
    with app.app_context():
        student = db.session.get(User, seeded_assignment["student_id"])
        try:
            assignment_service.get_assignment_for_student(seeded_assignment["other_assignment_id"], student)
            assert False, "Expected PermissionError"
        except PermissionError:
            assert True


def test_save_draft_after_submitted_raises_value_error(app, seeded_assignment):
    """Saving draft after submission must raise ValueError."""
    with app.app_context():
        student = db.session.get(User, seeded_assignment["student_id"])
        submission = AssignmentSubmission.query.filter_by(
            assignment_id=seeded_assignment["assignment_id"],
            student_id=student.id,
        ).first()
        submission.content = "Submitted answer"
        db.session.add(submission)
        db.session.commit()
        assignment_service.submit(submission.id, student)

        try:
            assignment_service.save_draft(submission.id, "Edit after submit", student)
            assert False, "Expected ValueError"
        except ValueError:
            assert True
