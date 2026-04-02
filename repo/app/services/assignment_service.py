from datetime import datetime, timezone

from app.extensions import db
from app.models.assignment import Assignment, AssignmentGrade, AssignmentSubmission, CohortMember
from app.models.user import User
from app.services import rbac_service


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_assignments_for_student(student) -> list[Assignment]:
    """Returns published assignments for cohorts the student belongs to."""
    cohort_ids = [
        row.cohort_id
        for row in CohortMember.query.filter_by(user_id=student.id, role_in_cohort="student").all()
    ]
    if not cohort_ids:
        return []
    return (
        Assignment.query.filter(Assignment.cohort_id.in_(cohort_ids), Assignment.status == "published")
        .order_by(Assignment.id.desc())
        .all()
    )


def get_assignment_for_student(assignment_id: int, student) -> Assignment:
    """Returns the Assignment if student belongs to its cohort, raises PermissionError otherwise."""
    assignment = Assignment.query.get_or_404(assignment_id)
    membership = CohortMember.query.filter_by(
        cohort_id=assignment.cohort_id,
        user_id=student.id,
        role_in_cohort="student",
    ).first()
    if not membership:
        raise PermissionError("forbidden")
    return assignment


def get_or_create_draft(assignment_id: int, student_id: int) -> AssignmentSubmission:
    """Get existing submission or create a blank draft."""
    submission = AssignmentSubmission.query.filter_by(assignment_id=assignment_id, student_id=student_id).first()
    if submission:
        return submission
    submission = AssignmentSubmission(
        assignment_id=assignment_id,
        student_id=student_id,
        content="",
        status="draft",
    )
    db.session.add(submission)
    db.session.commit()
    return submission


def save_draft(submission_id: int, content: str, student) -> AssignmentSubmission:
    """Save content as draft. Raises PermissionError if not the owner. Raises ValueError if already submitted."""
    submission = AssignmentSubmission.query.get_or_404(submission_id)
    if submission.student_id != student.id:
        raise PermissionError("forbidden")
    if submission.status in {"submitted", "graded"}:
        raise ValueError("Submission already finalized.")
    submission.content = (content or "").strip()
    db.session.add(submission)
    db.session.commit()
    return submission


def submit(submission_id: int, student) -> AssignmentSubmission:
    """Mark submission as submitted. Raises ValueError if content is empty or already submitted."""
    submission = AssignmentSubmission.query.get_or_404(submission_id)
    if submission.student_id != student.id:
        raise PermissionError("forbidden")
    if submission.status in {"submitted", "graded"}:
        raise ValueError("Assignment already submitted.")
    if not (submission.content or "").strip():
        raise ValueError("Submission content cannot be empty.")
    submission.status = "submitted"
    submission.submitted_at = _now()
    db.session.add(submission)
    db.session.commit()
    return submission


def get_submissions_for_grader(grader, effective_role: str | None = None) -> list:
    """Returns all submitted/graded submissions for cohorts the grader can access."""
    cohort_ids = [c.id for c in rbac_service.get_accessible_cohorts(grader, effective_role=effective_role)]
    if not cohort_ids:
        return []

    rows = (
        db.session.query(AssignmentSubmission, Assignment)
        .join(Assignment, Assignment.id == AssignmentSubmission.assignment_id)
        .filter(
            Assignment.cohort_id.in_(cohort_ids),
            AssignmentSubmission.status.in_(["submitted", "graded"]),
        )
        .order_by(AssignmentSubmission.submitted_at.desc(), AssignmentSubmission.id.desc())
        .all()
    )

    out = []
    for submission, assignment in rows:
        student = db.session.get(User, submission.student_id)
        grade = AssignmentGrade.query.filter_by(submission_id=submission.id).first()
        out.append(
            {
                "submission": submission,
                "assignment": assignment,
                "student": student,
                "grade": grade,
            }
        )
    return out


def grade_submission(submission_id: int, score: float, feedback: str, grader, effective_role: str | None = None) -> AssignmentGrade:
    """Create or update grade. Raises PermissionError if grader cannot access the cohort.
    Raises ValueError if score > assignment.max_score or score < 0."""
    submission = AssignmentSubmission.query.get_or_404(submission_id)
    assignment = Assignment.query.get_or_404(submission.assignment_id)

    if not rbac_service.can_access_cohort(grader, assignment.cohort_id, effective_role=effective_role):
        raise PermissionError("forbidden")

    score_val = float(score)
    if score_val < 0:
        raise ValueError("Score cannot be negative.")
    if score_val > float(assignment.max_score or 100.0):
        raise ValueError("Score exceeds assignment max score.")

    grade = AssignmentGrade.query.filter_by(submission_id=submission.id).first()
    if not grade:
        grade = AssignmentGrade(submission_id=submission.id, grader_id=grader.id)

    grade.grader_id = grader.id
    grade.score = score_val
    grade.feedback = (feedback or "").strip() or None
    grade.graded_at = _now()
    submission.status = "graded"

    db.session.add(grade)
    db.session.add(submission)
    db.session.commit()
    return grade


def get_assignment_list_for_admin(cohort_id: int | None = None) -> list[Assignment]:
    """Returns all assignments, optionally filtered by cohort."""
    query = Assignment.query
    if cohort_id is not None:
        query = query.filter(Assignment.cohort_id == cohort_id)
    return query.order_by(Assignment.id.desc()).all()


def create_assignment(
    title: str,
    description: str,
    cohort_id: int,
    creator_id: int,
    due_date_str: str | None,
    max_score: float,
) -> Assignment:
    """Validate and create a new assignment in draft status."""
    clean_title = (title or "").strip()
    if not clean_title:
        raise ValueError("Title is required.")
    if float(max_score) <= 0:
        raise ValueError("Max score must be greater than zero.")

    due_date = None
    if due_date_str:
        due_date = datetime.fromisoformat(due_date_str)

    row = Assignment(
        title=clean_title,
        description=(description or "").strip() or None,
        cohort_id=int(cohort_id),
        creator_id=int(creator_id),
        status="draft",
        due_date=due_date,
        max_score=float(max_score),
    )
    db.session.add(row)
    db.session.commit()
    return row


def publish_assignment(assignment_id: int) -> Assignment:
    """Change status from draft to published."""
    assignment = Assignment.query.get_or_404(assignment_id)
    if assignment.status != "draft":
        raise ValueError("Only draft assignments can be published.")
    assignment.status = "published"
    db.session.add(assignment)
    db.session.commit()
    return assignment


def close_assignment(assignment_id: int) -> Assignment:
    """Change status from published to closed."""
    assignment = Assignment.query.get_or_404(assignment_id)
    if assignment.status != "published":
        raise ValueError("Only published assignments can be closed.")
    assignment.status = "closed"
    db.session.add(assignment)
    db.session.commit()
    return assignment
