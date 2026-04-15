"""Real HTTP test harness — requests.Session against live Flask server."""
import os
import socket
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
import requests

from app import create_app
from app.extensions import db
from app.models.assignment import CohortMember
from app.models.org import Class, Cohort, Major, School
from app.models.paper import Paper, PaperQuestion
from app.models.question import Question
from app.models.user import User
from app.services.auth_service import hash_password
from app.services.org_setup import ensure_department_hierarchy, get_or_create_default_subdepartment


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def http_app():
    """Create a testing Flask app with in-memory SQLite."""
    os.environ.setdefault("SECRET_KEY", "http-test-secret-key-32chars-long")
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        ensure_department_hierarchy()
    return app


@pytest.fixture(scope="module")
def live_server(http_app):
    """Start a real Flask HTTP server in a background thread."""
    port = _free_port()
    http_app.config["E2E_PORT"] = port

    def _run():
        http_app.run(host="127.0.0.1", port=port, use_reloader=False, threaded=True)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    # Wait for server to be ready
    for _ in range(30):
        try:
            requests.get(f"http://127.0.0.1:{port}/health", timeout=0.5)
            break
        except Exception:
            time.sleep(0.2)
    yield f"http://127.0.0.1:{port}"


@pytest.fixture(scope="module")
def seeded(http_app):
    """Seed the in-memory DB with standard test data. Returns IDs dict."""
    with http_app.app_context():
        def _user(username, role, pw):
            u = User.query.filter_by(username=username).first()
            if not u:
                u = User(
                    username=username,
                    password_hash=hash_password(pw),
                    role=role,
                    is_active=True,
                )
                db.session.add(u)
                db.session.flush()
            return u

        admin = _user("h_admin", "dept_admin", "Admin@Practicum1")
        advisor = _user("h_advisor", "faculty_advisor", "Advisor@Practicum1")
        student = _user("h_student", "student", "Student@Practicum1")
        student2 = _user("h_student2", "student", "Student@Practicum1")

        school = School.query.filter_by(code="HS").first()
        if not school:
            school = School(name="HTTP School", code="HS", is_active=True)
            db.session.add(school)
            db.session.flush()
        sub = get_or_create_default_subdepartment(school.id)

        major = Major.query.filter_by(code="HM").first()
        if not major:
            major = Major(
                name="HTTP Major", code="HM", school_id=school.id, sub_department_id=sub.id
            )
            db.session.add(major)
            db.session.flush()

        clazz = Class.query.filter_by(name="HTTP Class").first()
        if not clazz:
            clazz = Class(name="HTTP Class", year=2026, major_id=major.id)
            db.session.add(clazz)
            db.session.flush()

        cohort = Cohort.query.filter_by(name="HTTP Cohort").first()
        if not cohort:
            cohort = Cohort(
                name="HTTP Cohort",
                class_id=clazz.id,
                internship_term="2026",
                is_active=True,
            )
            db.session.add(cohort)
            db.session.flush()

        # Add cohort members if not already present
        if not CohortMember.query.filter_by(cohort_id=cohort.id, user_id=advisor.id).first():
            db.session.add(
                CohortMember(cohort_id=cohort.id, user_id=advisor.id, role_in_cohort="faculty_advisor")
            )
        if not CohortMember.query.filter_by(cohort_id=cohort.id, user_id=student.id).first():
            db.session.add(
                CohortMember(cohort_id=cohort.id, user_id=student.id, role_in_cohort="student")
            )

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        q = Question.query.filter_by(stem="HTTP Q?").first()
        if not q:
            q = Question(
                creator_id=admin.id,
                school_id=school.id,
                question_type="single_choice",
                stem="HTTP Q?",
                options='[{"key":"A","text":"A"},{"key":"B","text":"B"},{"key":"C","text":"C"},{"key":"D","text":"D"}]',
                correct_answer="A",
                score_points=5,
                is_active=True,
            )
            db.session.add(q)
            db.session.flush()

        paper = Paper.query.filter_by(title="HTTP Paper").first()
        if not paper:
            paper = Paper(
                title="HTTP Paper",
                cohort_id=cohort.id,
                creator_id=admin.id,
                status="published",
                time_limit_min=45,
                max_attempts=2,
                total_score=5,
                available_from=now - timedelta(hours=1),
                available_until=now + timedelta(hours=2),
            )
            db.session.add(paper)
            db.session.flush()
            db.session.add(
                PaperQuestion(paper_id=paper.id, question_id=q.id, order_index=1, score_points=5)
            )
        db.session.commit()

        return {
            "admin_id": admin.id,
            "advisor_id": advisor.id,
            "student_id": student.id,
            "student2_id": student2.id,
            "cohort_id": cohort.id,
            "paper_id": paper.id,
            "question_id": q.id,
            "school_id": school.id,
        }


@pytest.fixture
def http_session(live_server):
    """A requests.Session connected to the live server. Does NOT pre-login."""
    s = requests.Session()
    s.base_url = live_server
    yield s
    s.close()


def http_login(session, base_url, username, password):
    """POST /login and follow redirects. Returns response."""
    resp = session.post(
        f"{base_url}/login",
        data={"username": username, "password": password},
        allow_redirects=True,
    )
    return resp


def http_reauth(session, base_url, password, action_url=None):
    """Complete a reauth cycle: trigger action (if given), then POST /reauth."""
    if action_url:
        session.get(f"{base_url}{action_url}", allow_redirects=False)
    resp = session.post(
        f"{base_url}/reauth",
        data={"password": password, "next_url": action_url or "/dashboard"},
        allow_redirects=True,
    )
    return resp
