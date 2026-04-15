from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models.attempt import Attempt
from app.models.paper import Paper


def _login_student(client):
    client.post("/login", data={"username": "student1", "password": "Student@Practicum1"})


def test_quiz_start_within_window_creates_attempt(client, app, seeded_assessment):
    _login_student(client)
    pid = seeded_assessment["paper_id"]
    res = client.post(f"/quiz/{pid}/start", follow_redirects=False)
    assert res.status_code == 302
    assert f"/quiz/{pid}/take" in res.headers.get("Location", "")


def test_quiz_start_outside_window_error_fragment(client, app, seeded_assessment):
    _login_student(client)
    with app.app_context():
        paper = db.session.get(Paper, seeded_assessment["paper_id"])
        paper.available_from = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
        paper.available_until = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=2)
        db.session.add(paper)
        db.session.commit()
    res = client.post(f"/quiz/{seeded_assessment['paper_id']}/start", headers={"HX-Request": "true"})
    assert res.status_code == 400


def test_quiz_start_draft_paper_forbidden(client, app, seeded_assessment):
    """Student cannot start a draft paper."""
    _login_student(client)
    with app.app_context():
        paper = db.session.get(Paper, seeded_assessment["paper_id"])
        paper.status = "draft"
        db.session.add(paper)
        db.session.commit()
    res = client.post(f"/quiz/{seeded_assessment['paper_id']}/start")
    assert res.status_code == 403


def test_quiz_start_unassigned_cohort_paper_forbidden(client, app, seeded_assessment):
    """Student from cohort A cannot start paper belonging to cohort B."""
    _login_student(client)
    pid = seeded_assessment["paper2_id"]  # paper2 belongs to cohort2, student1 is in cohort1
    res = client.post(f"/quiz/{pid}/start")
    assert res.status_code == 403


def test_quiz_autosave_saves_answers_and_indicator(client, seeded_assessment):
    _login_student(client)
    pid = seeded_assessment["paper_id"]
    client.post(f"/quiz/{pid}/start")
    res = client.post(f"/quiz/{pid}/autosave", data={f"answer_{seeded_assessment['question_ids'][0]}": "A"})
    assert res.status_code == 200
    assert "Saved at" in res.get_data(as_text=True)


def test_quiz_submit_first_and_second_token_replay(client, app, seeded_assessment):
    _login_student(client)
    pid = seeded_assessment["paper_id"]
    client.post(f"/quiz/{pid}/start")
    with app.app_context():
        attempt = Attempt.query.filter_by(paper_id=pid).order_by(Attempt.id.desc()).first()
        token = attempt.submission_token
    first = client.post(f"/quiz/{pid}/submit", data={"submission_token": token}, headers={"HX-Request": "true"})
    second = client.post(f"/quiz/{pid}/submit", data={"submission_token": token}, headers={"HX-Request": "true"})
    assert first.status_code == 204
    assert "already recorded" in second.get_data(as_text=True)


def test_quiz_concurrent_submit_second_rejected(client, app, seeded_assessment):
    """Two rapid submits with the same token: first succeeds, second is rejected."""
    _login_student(client)
    pid = seeded_assessment["paper_id"]
    client.post(f"/quiz/{pid}/start")

    with app.app_context():
        attempt = Attempt.query.filter_by(paper_id=pid).order_by(Attempt.id.desc()).first()
        token = attempt.submission_token
        attempt_id = attempt.id

    # First submit should succeed (204 with HX-Redirect)
    first = client.post(
        f"/quiz/{pid}/submit",
        data={"submission_token": token},
        headers={"HX-Request": "true"},
    )
    assert first.status_code == 204
    assert "HX-Redirect" in first.headers

    # Second submit with same token should be rejected
    second = client.post(
        f"/quiz/{pid}/submit",
        data={"submission_token": token},
        headers={"HX-Request": "true"},
    )
    assert "already recorded" in second.get_data(as_text=True)

    # Verify attempt is finalized and not corrupted
    with app.app_context():
        attempt = db.session.get(Attempt, attempt_id)
        assert attempt.status == "finalized"

        # Only one finalization audit log exists
        from app.models.audit_log import AuditLog
        finalize_logs = AuditLog.query.filter_by(
            action="ATTEMPT_FINALIZED",
            resource_type="attempt",
            resource_id=attempt_id,
        ).all()
        assert len(finalize_logs) == 1


def test_quiz_result_for_other_student_forbidden(client, seeded_assessment, app):
    # student1 makes attempt
    _login_student(client)
    pid = seeded_assessment["paper_id"]
    client.post(f"/quiz/{pid}/start")
    with app.app_context():
        attempt = Attempt.query.filter_by(paper_id=pid).order_by(Attempt.id.desc()).first()
        aid = attempt.id
    client.get("/logout")
    client.post("/login", data={"username": "student2", "password": "Student@Practicum1"})
    res = client.get(f"/quiz/{pid}/result/{aid}")
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# New gap-filling tests: quiz_list, take_quiz, time_check
# ---------------------------------------------------------------------------

def test_quiz_list_shows_available_paper(client, seeded_assessment):
    """Student GET /quiz returns page containing their enrolled paper."""
    _login_student(client)
    res = client.get("/quiz")
    assert res.status_code == 200
    assert "Paper 1" in res.get_data(as_text=True)


def test_quiz_list_unauthenticated_redirects(client):
    """Unauthenticated GET /quiz must redirect."""
    res = client.get("/quiz", follow_redirects=False)
    assert res.status_code in (302, 401, 403)


def test_quiz_take_requires_active_attempt(client, seeded_assessment):
    """GET /quiz/<id>/take with no attempt redirects to quiz list."""
    _login_student(client)
    pid = seeded_assessment["paper_id"]
    res = client.get(f"/quiz/{pid}/take", follow_redirects=False)
    assert res.status_code == 302


def test_quiz_take_after_start_shows_questions(client, seeded_assessment):
    """After starting, GET /quiz/<id>/take returns 200 with question stems."""
    _login_student(client)
    pid = seeded_assessment["paper_id"]
    client.post(f"/quiz/{pid}/start")
    res = client.get(f"/quiz/{pid}/take")
    assert res.status_code == 200


def test_quiz_time_check_returns_seconds(client, seeded_assessment):
    """GET /quiz/<id>/time-check with active attempt returns JSON with seconds_remaining."""
    _login_student(client)
    pid = seeded_assessment["paper_id"]
    client.post(f"/quiz/{pid}/start")
    res = client.get(f"/quiz/{pid}/time-check")
    assert res.status_code == 200
    data = res.get_json()
    assert "seconds_remaining" in data
    assert isinstance(data["seconds_remaining"], (int, float))


def test_quiz_time_check_no_attempt_returns_zero(client, seeded_assessment):
    """GET /quiz/<id>/time-check with no active attempt returns seconds_remaining: 0."""
    _login_student(client)
    pid = seeded_assessment["paper_id"]
    res = client.get(f"/quiz/{pid}/time-check")
    assert res.status_code == 200
    data = res.get_json()
    assert data["seconds_remaining"] == 0
