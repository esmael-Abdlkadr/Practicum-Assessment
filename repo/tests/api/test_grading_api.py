from app.extensions import db
from app.models.attempt import Attempt, AttemptAnswer
from app.models.paper import Paper
from app.models.question import Question
from app.models.user import User
from app.services import grading_service


def _prepare_attempt(app, seeded_assessment):
    with app.app_context():
        student = User.query.filter_by(username="student1").first()
        paper = db.session.get(Paper, seeded_assessment["paper_id"])
        q_subj = db.session.get(Question, seeded_assessment["question_ids"][4])
        attempt = Attempt(paper_id=paper.id, student_id=student.id, status="in_progress", time_limit_min=45)
        db.session.add(attempt)
        db.session.flush()
        db.session.add(AttemptAnswer(attempt_id=attempt.id, question_id=q_subj.id, answer="essay"))
        db.session.commit()
        grading_service.auto_grade(attempt)
        return attempt.id, q_subj.id, paper.id


def test_get_grading_dashboard_only_assigned_cohorts(client, app, seeded_assessment):
    attempt_id, qid, pid = _prepare_attempt(app, seeded_assessment)
    client.post("/login", data={"username": "advisor1", "password": "Advisor@Practicum1"})
    res = client.get("/grading")
    assert res.status_code == 200
    assert "Paper 1" in res.get_data(as_text=True)


def test_post_grading_score_valid_returns_fragment(client, app, seeded_assessment):
    attempt_id, qid, _ = _prepare_attempt(app, seeded_assessment)
    client.post("/login", data={"username": "advisor1", "password": "Advisor@Practicum1"})
    res = client.post(f"/grading/attempt/{attempt_id}/question/{qid}/score", data={"score": "3"}, headers={"HX-Request": "true"})
    assert res.status_code == 200
    assert "manually_graded" in res.get_data(as_text=True)


def test_post_grading_score_over_max_validation_error(client, app, seeded_assessment):
    attempt_id, qid, _ = _prepare_attempt(app, seeded_assessment)
    client.post("/login", data={"username": "advisor1", "password": "Advisor@Practicum1"})
    res = client.post(f"/grading/attempt/{attempt_id}/question/{qid}/score", data={"score": "999"}, headers={"HX-Request": "true"})
    assert res.status_code == 400


def test_post_grading_comment_adds_thread_fragment(client, app, seeded_assessment):
    attempt_id, qid, _ = _prepare_attempt(app, seeded_assessment)
    client.post("/login", data={"username": "advisor1", "password": "Advisor@Practicum1"})
    res = client.post(
        f"/grading/attempt/{attempt_id}/question/{qid}/comment",
        data={"comment_text": "Looks good"},
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 200
    assert "Looks good" in res.get_data(as_text=True)


def test_grader_cannot_score_question_not_in_paper(client, app, seeded_assessment):
    """POSTing a score for a question that does not belong to the attempt's paper
    must return 404 or 403 — not silently succeed."""
    from app.models.attempt import Attempt
    from app.models.question import Question

    client.post("/login", data={"username": "advisor1", "password": "Advisor@Practicum1"})

    with app.app_context():
        attempt = Attempt(
            paper_id=seeded_assessment["paper_id"],
            student_id=seeded_assessment["student_id"],
            status="submitted",
            submission_token=None,
        )
        db.session.add(attempt)

        base_q = db.session.get(Question, seeded_assessment["question_ids"][0])
        foreign_q = Question(
            creator_id=seeded_assessment["admin_id"],
            school_id=base_q.school_id,
            question_type="short_answer",
            stem="Foreign question",
            correct_answer=None,
            score_points=5,
            is_active=True,
        )
        db.session.add(foreign_q)
        db.session.commit()
        attempt_id = attempt.id
        foreign_q_id = foreign_q.id

    res = client.post(
        f"/grading/attempt/{attempt_id}/question/{foreign_q_id}/score",
        data={"score": "3"},
        headers={"HX-Request": "true"},
    )
    assert res.status_code in (400, 403, 404), (
        f"Expected 400/403/404 for foreign question, got {res.status_code}"
    )


def test_advisor_cannot_grade_attempt_in_unassigned_cohort(client, app, seeded_assessment):
    """An advisor assigned to cohort A must get 403 when trying to grade an attempt
    in cohort B (where they are not a member)."""
    from app.models.attempt import Attempt

    client.post("/login", data={"username": "advisor1", "password": "Advisor@Practicum1"})

    with app.app_context():
        attempt = Attempt(
            paper_id=seeded_assessment["paper2_id"],
            student_id=seeded_assessment["student2_id"],
            status="submitted",
            submission_token=None,
        )
        db.session.add(attempt)
        db.session.commit()
        attempt_id = attempt.id

    res = client.get(f"/grading/attempt/{attempt_id}")
    assert res.status_code == 403


def test_advisor_cannot_access_report_for_unassigned_cohort_paper(client, app, seeded_assessment):
    """An advisor assigned to cohort A must get 403 on paper report for cohort B."""
    client.post("/login", data={"username": "advisor1", "password": "Advisor@Practicum1"})
    paper2_id = seeded_assessment["paper2_id"]
    res = client.get(f"/reports/paper/{paper2_id}")
    assert res.status_code == 403
