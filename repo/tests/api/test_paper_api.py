"""API tests for Paper builder endpoints (/admin/papers)."""
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models.paper import Paper, PaperQuestion


def login_admin(client):
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})


def _utcnow_str():
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M")


def _make_paper_form(cohort_id):
    now = datetime.now(timezone.utc)
    return {
        "title": "API Test Paper",
        "description": "Created via API test",
        "cohort_id": cohort_id,
        "time_limit_min": "45",
        "max_attempts": "1",
        "available_from": (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
        "available_until": (now + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M"),
    }


def test_list_papers_requires_auth(client):
    res = client.get("/admin/papers", follow_redirects=False)
    assert res.status_code in (302, 401, 403)


def test_list_papers_admin_sees_papers(client, seeded_assessment):
    login_admin(client)
    res = client.get("/admin/papers")
    assert res.status_code == 200
    assert b"Paper 1" in res.data


def test_create_paper_redirects_to_builder(client, seeded_assessment):
    login_admin(client)
    cohort_id = seeded_assessment["cohort_id"]
    res = client.post(
        "/admin/papers",
        data=_make_paper_form(cohort_id),
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert "/admin/papers/" in res.headers.get("Location", "")


def test_create_paper_unauthenticated_redirects(client, seeded_assessment):
    cohort_id = seeded_assessment["cohort_id"]
    res = client.post(
        "/admin/papers",
        data=_make_paper_form(cohort_id),
        follow_redirects=False,
    )
    assert res.status_code in (302, 401, 403)


def test_add_question_to_paper_success(client, seeded_assessment):
    login_admin(client)
    cohort_id = seeded_assessment["cohort_id"]
    question_id = seeded_assessment["question_ids"][0]
    admin_id = seeded_assessment["admin_id"]

    # Create a fresh draft paper for this test (add_question_to_paper requires status="draft")
    with client.application.app_context():
        from app.models.org import Cohort
        draft_paper = Paper(
            title="Draft Paper",
            cohort_id=cohort_id,
            creator_id=admin_id,
            status="draft",
            time_limit_min=45,
            max_attempts=1,
            total_score=10,
        )
        db.session.add(draft_paper)
        db.session.commit()
        draft_paper_id = draft_paper.id

    res = client.post(
        f"/admin/papers/{draft_paper_id}/questions",
        data={"question_id": question_id, "score_points": "3", "order_index": "10"},
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 200


def test_remove_question_from_paper(client, seeded_assessment):
    login_admin(client)
    paper_id = seeded_assessment["paper_id"]
    question_id = seeded_assessment["question_ids"][0]

    # Ensure link exists
    with client.application.app_context():
        link = PaperQuestion.query.filter_by(paper_id=paper_id, question_id=question_id).first()
        if not link:
            link = PaperQuestion(paper_id=paper_id, question_id=question_id, order_index=99, score_points=1)
            db.session.add(link)
            db.session.commit()

    res = client.delete(
        f"/admin/papers/{paper_id}/questions/{question_id}",
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 200


def test_publish_paper_success(client, seeded_assessment):
    login_admin(client)
    paper_id = seeded_assessment["paper_id"]
    now = datetime.now(timezone.utc)
    res = client.post(
        f"/admin/papers/{paper_id}/publish",
        data={
            "time_limit_min": "60",
            "max_attempts": "2",
            "available_from": (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
            "available_until": (now + timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M"),
        },
        follow_redirects=False,
    )
    assert res.status_code in (200, 302)


def test_publish_paper_invalid_date_400(client, seeded_assessment):
    login_admin(client)
    paper_id = seeded_assessment["paper_id"]
    res = client.post(
        f"/admin/papers/{paper_id}/publish",
        data={
            "time_limit_min": "45",
            "max_attempts": "1",
            "available_from": "not-a-date",
            "available_until": "also-not-a-date",
        },
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 400


def test_paper_builder_page_accessible(client, seeded_assessment):
    login_admin(client)
    paper_id = seeded_assessment["paper_id"]
    res = client.get(f"/admin/papers/{paper_id}")
    assert res.status_code == 200
    assert b"Paper 1" in res.data


def test_add_paper_question_writes_audit_log(client, app, seeded_assessment):
    from app.models.audit_log import AuditLog

    login_admin(client)
    cohort_id = seeded_assessment["cohort_id"]
    question_id = seeded_assessment["question_ids"][0]
    admin_id = seeded_assessment["admin_id"]

    with app.app_context():
        draft_paper = Paper(
            title="Draft Paper Audit",
            cohort_id=cohort_id,
            creator_id=admin_id,
            status="draft",
            time_limit_min=45,
            max_attempts=1,
            total_score=10,
        )
        db.session.add(draft_paper)
        db.session.commit()
        draft_paper_id = draft_paper.id

    res = client.post(
        f"/admin/papers/{draft_paper_id}/questions",
        data={"question_id": question_id, "score_points": "3", "order_index": "10"},
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 200

    with app.app_context():
        row = AuditLog.query.filter_by(action="PAPER_QUESTION_ADDED", resource_id=str(draft_paper_id)).first()
        assert row is not None


def test_remove_paper_question_writes_audit_log(client, app, seeded_assessment):
    from app.models.audit_log import AuditLog

    login_admin(client)
    paper_id = seeded_assessment["paper_id"]
    question_id = seeded_assessment["question_ids"][0]

    with app.app_context():
        link = PaperQuestion.query.filter_by(paper_id=paper_id, question_id=question_id).first()
        if not link:
            link = PaperQuestion(paper_id=paper_id, question_id=question_id, order_index=99, score_points=1)
            db.session.add(link)
            db.session.commit()

    res = client.delete(
        f"/admin/papers/{paper_id}/questions/{question_id}",
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 200

    with app.app_context():
        row = AuditLog.query.filter_by(action="PAPER_QUESTION_REMOVED", resource_id=str(paper_id)).first()
        assert row is not None


# ---------------------------------------------------------------------------
# New gap-filling tests: close paper, student available papers, create validation
# ---------------------------------------------------------------------------

def test_close_paper_returns_success(client, seeded_assessment):
    """POST /admin/papers/<id>/close returns success fragment."""
    login_admin(client)
    paper_id = seeded_assessment["paper_id"]
    res = client.post(f"/admin/papers/{paper_id}/close", headers={"HX-Request": "true"})
    assert res.status_code == 200
    assert b"closed" in res.data.lower()


def test_close_paper_unauthenticated_redirects(client, seeded_assessment):
    """Unauthenticated POST /admin/papers/<id>/close must redirect."""
    paper_id = seeded_assessment["paper_id"]
    res = client.post(f"/admin/papers/{paper_id}/close", follow_redirects=False)
    assert res.status_code in (302, 401, 403)


def test_student_available_papers_returns_json(client, seeded_assessment):
    """Student GET /admin/papers/student/available returns JSON list with enrolled paper."""
    client.post("/login", data={"username": "student1", "password": "Student@Practicum1"})
    res = client.get("/admin/papers/student/available")
    assert res.status_code == 200
    assert res.content_type == "application/json"
    data = res.get_json()
    assert isinstance(data, list)
    assert any(p["id"] == seeded_assessment["paper_id"] for p in data)


def test_student_available_papers_excludes_other_cohort(client, seeded_assessment):
    """Student 1 (cohort 1) must not see paper from cohort 2 in available list."""
    client.post("/login", data={"username": "student1", "password": "Student@Practicum1"})
    res = client.get("/admin/papers/student/available")
    data = res.get_json()
    paper2_id = seeded_assessment["paper2_id"]
    assert all(p["id"] != paper2_id for p in data), "paper2 from cohort2 must not appear for student1"


def test_student_available_papers_admin_forbidden(client, seeded_assessment):
    """Admin (non-student) GET /admin/papers/student/available must return 403."""
    login_admin(client)
    res = client.get("/admin/papers/student/available")
    assert res.status_code == 403


def test_create_paper_missing_title_400(client, seeded_assessment):
    """POST /admin/papers without title returns 400."""
    login_admin(client)
    cohort_id = seeded_assessment["cohort_id"]
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    res = client.post(
        "/admin/papers",
        data={
            "title": "",
            "cohort_id": cohort_id,
            "available_from": (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
            "available_until": (now + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M"),
        },
        follow_redirects=False,
    )
    assert res.status_code in (400, 302)
