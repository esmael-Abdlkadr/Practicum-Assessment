"""API tests for Question CRUD endpoints (/admin/questions)."""
import json

from app.extensions import db
from app.models.question import Question


def login_admin(client):
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})


def _base_form(school_id):
    return {
        "question_type": "single_choice",
        "stem": "What is 2+2?",
        "options_text": "4|3|5|6",
        "correct_answer": "A",
        "score_points": "2",
        "difficulty": "easy",
        "school_id": school_id,
        "tags_text": "math",
    }


def test_create_question_success(client, seeded_assessment):
    login_admin(client)
    sid = seeded_assessment["admin_id"]  # school exists in seeded_assessment
    # Get real school_id from seeded_assessment context
    from app.models.org import School
    with client.application.app_context():
        school = School.query.first()
        school_id = school.id

    res = client.post(
        "/admin/questions",
        data=_base_form(school_id),
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 200


def test_create_question_unauthenticated_redirects(client):
    res = client.post(
        "/admin/questions",
        data={"question_type": "fill_in", "stem": "X", "score_points": "1"},
        follow_redirects=False,
    )
    assert res.status_code in (302, 401, 403)


def test_update_question_success(client, seeded_assessment):
    login_admin(client)
    qid = seeded_assessment["question_ids"][0]  # single_choice question
    res = client.put(
        f"/admin/questions/{qid}",
        data={
            "question_type": "single_choice",
            "stem": "Updated stem?",
            "options_text": "Yes|No",
            "correct_answer": "A",
            "score_points": "3",
            "difficulty": "medium",
            "school_id": "",
            "tags_text": "",
        },
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 200


def test_update_question_nonexistent_404(client, admin_user):
    login_admin(client)
    res = client.put(
        "/admin/questions/99999",
        data={
            "question_type": "fill_in",
            "stem": "Ghost question",
            "correct_answer": "none",
            "score_points": "1",
            "difficulty": "easy",
            "school_id": "",
            "tags_text": "",
        },
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 404


def test_delete_question_soft_deletes(client, app, seeded_assessment):
    login_admin(client)
    qid = seeded_assessment["question_ids"][4]  # short_answer
    res = client.delete(
        f"/admin/questions/{qid}",
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 200
    with app.app_context():
        q = db.session.get(Question, qid)
        assert q is None or q.is_active is False


def test_list_questions_requires_auth(client):
    res = client.get("/admin/questions", follow_redirects=False)
    assert res.status_code in (302, 401, 403)


def test_rubric_save_success(client, seeded_assessment):
    login_admin(client)
    qid = seeded_assessment["question_ids"][4]  # short_answer
    res = client.post(
        f"/admin/questions/{qid}/rubric",
        data={"criteria": "Award 1 point per correct element."},
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 200
    assert b"Rubric saved" in res.data


def test_rubric_save_missing_criteria_400(client, seeded_assessment):
    login_admin(client)
    qid = seeded_assessment["question_ids"][4]
    res = client.post(
        f"/admin/questions/{qid}/rubric",
        data={"criteria": ""},
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 400


def test_rubric_save_writes_audit_log(client, app, seeded_assessment):
    from app.models.audit_log import AuditLog

    login_admin(client)
    qid = seeded_assessment["question_ids"][4]
    res = client.post(
        f"/admin/questions/{qid}/rubric",
        data={"criteria": "Audit criteria text."},
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 200
    with app.app_context():
        row = AuditLog.query.filter_by(action="RUBRIC_SAVED", resource_id=str(qid)).first()
        assert row is not None
