from app.extensions import db
from app.models.assignment import Assignment, AssignmentSubmission
from app.models.user import User


def _login_student(client, username="student1", password="Student@Practicum1"):
    client.post("/login", data={"username": username, "password": password})


def _login_admin(client):
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})


def _login_advisor(client):
    client.post("/login", data={"username": "advisor1", "password": "Advisor@Practicum1"})


def _ensure_submission_ready(app, seeded_assignment, student_username="student1"):
    with app.app_context():
        student = User.query.filter_by(username=student_username).first()
        submission = AssignmentSubmission.query.filter_by(
            assignment_id=seeded_assignment["assignment_id"],
            student_id=student.id,
        ).first()
        submission.content = "Final answer"
        submission.status = "submitted"
        db.session.add(submission)
        db.session.commit()
        return submission.id


def test_student_sees_published_assignment(client, app, seeded_assignment):
    """Student GET /assignments returns the published assignment."""
    _login_student(client)
    res = client.get("/assignments")
    assert res.status_code == 200
    assert "Weekly Reflection" in res.get_data(as_text=True)


def test_student_cannot_see_other_cohort_assignment(client, app, seeded_assignment):
    """Student from cohort A cannot see assignments from cohort B."""
    _login_student(client)
    res = client.get(f"/assignments/{seeded_assignment['other_assignment_id']}")
    assert res.status_code == 403


def test_student_can_save_draft(client, app, seeded_assignment):
    """POST /assignments/<id>/save returns Saved at fragment."""
    _login_student(client)
    res = client.post(f"/assignments/{seeded_assignment['assignment_id']}/save", data={"content": "Draft text"})
    assert res.status_code == 200
    assert "Saved at" in res.get_data(as_text=True)


def test_student_can_submit(client, app, seeded_assignment):
    """POST /assignments/<id>/submit with content returns 200 and confirms submission."""
    _login_student(client)
    res = client.post(f"/assignments/{seeded_assignment['assignment_id']}/submit", data={"content": "My final answer"})
    assert res.status_code == 200
    assert "Submission received" in res.get_data(as_text=True)


def test_student_cannot_submit_empty(client, app, seeded_assignment):
    """POST /assignments/<id>/submit with no content returns 400."""
    _login_student(client)
    res = client.post(f"/assignments/{seeded_assignment['assignment_id']}/submit", data={"content": ""})
    assert res.status_code == 400


def test_student_cannot_resubmit(client, app, seeded_assignment):
    """Second submit returns 400."""
    _login_student(client)
    client.post(f"/assignments/{seeded_assignment['assignment_id']}/submit", data={"content": "First submit"})
    res = client.post(f"/assignments/{seeded_assignment['assignment_id']}/submit", data={"content": "Second submit"})
    assert res.status_code == 400


def test_grader_sees_submission_in_list(client, app, seeded_assignment):
    """Advisor GET /assignments/grading shows submitted work."""
    _ensure_submission_ready(app, seeded_assignment)
    _login_advisor(client)
    res = client.get("/assignments/grading")
    assert res.status_code == 200
    assert "Weekly Reflection" in res.get_data(as_text=True)


def test_grader_can_grade(client, app, seeded_assignment):
    """Advisor POST /assignments/grading/<id>/grade with score and feedback returns 200."""
    submission_id = _ensure_submission_ready(app, seeded_assignment)
    _login_advisor(client)
    res = client.post(
        f"/assignments/grading/{submission_id}/grade",
        data={"score": "88", "feedback": "Good structure."},
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 200
    assert "Save Grade" in res.get_data(as_text=True)


def test_grader_cannot_grade_unassigned_cohort(client, app, seeded_assignment):
    """Advisor cannot grade submission from cohort they are not assigned to — expects 403."""
    with app.app_context():
        assignment_other = db.session.get(Assignment, seeded_assignment["other_assignment_id"])
        submission_other = AssignmentSubmission(
            assignment_id=assignment_other.id,
            student_id=seeded_assignment["student2_id"],
            content="Other cohort answer",
            status="submitted",
        )
        db.session.add(submission_other)
        db.session.commit()
        sid = submission_other.id

    _login_advisor(client)
    res = client.post(f"/assignments/grading/{sid}/grade", data={"score": "70", "feedback": "n/a"})
    assert res.status_code == 403


def test_admin_can_create_assignment(client, app, seeded_assignment):
    """Admin POST /admin/assignments returns row fragment with new assignment."""
    _login_admin(client)
    res = client.post(
        "/admin/assignments",
        data={
            "title": "New Admin Assignment",
            "description": "Desc",
            "cohort_id": str(seeded_assignment["cohort_id"]),
            "max_score": "100",
        },
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 200
    assert "New Admin Assignment" in res.get_data(as_text=True)


def test_admin_can_publish_assignment(client, app, seeded_assignment):
    """Admin POST /admin/assignments/<id>/publish changes status to published."""
    with app.app_context():
        draft = Assignment(
            title="Draft Assignment",
            description="d",
            cohort_id=seeded_assignment["cohort_id"],
            creator_id=seeded_assignment["student_id"],
            status="draft",
            max_score=100,
        )
        db.session.add(draft)
        db.session.commit()
        aid = draft.id

    _login_admin(client)
    res = client.post(f"/admin/assignments/{aid}/publish", headers={"HX-Request": "true"})
    assert res.status_code == 200
    with app.app_context():
        assert db.session.get(Assignment, aid).status == "published"


def test_student_cannot_access_grading_routes(client, app, seeded_assignment):
    """Student accessing /assignments/grading returns 403."""
    _login_student(client)
    res = client.get("/assignments/grading")
    assert res.status_code == 403
