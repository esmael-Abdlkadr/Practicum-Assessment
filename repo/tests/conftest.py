from datetime import datetime, timedelta, timezone

import pytest

from app import create_app
from app.extensions import db
from app.models.assignment import Assignment, AssignmentSubmission, CohortMember
from app.models.org import Class, Cohort, Major, School
from app.services.org_setup import ensure_department_hierarchy, get_or_create_default_subdepartment
from app.models.paper import Paper, PaperQuestion
from app.models.question import Question
from app.models.user import User
from app.services.auth_service import hash_password


@pytest.fixture
def app():
    application = create_app("testing")
    with application.app_context():
        import app.models  # noqa: F401

        db.drop_all()
        db.create_all()
        ensure_department_hierarchy()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def create_user(username: str, role: str, password: str = "Admin@Practicum1"):
    user = User(
        username=username,
        role=role,
        password_hash=hash_password(password),
        is_active=True,
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def admin_user(app):
    with app.app_context():
        return create_user("admin", "dept_admin")


@pytest.fixture
def dept_admin(admin_user):
    return admin_user


@pytest.fixture
def student_user(app):
    with app.app_context():
        return create_user("student1", "student", "Student@Practicum1")


@pytest.fixture
def student(student_user):
    return student_user


@pytest.fixture
def faculty_advisor(app):
    with app.app_context():
        return User.query.filter_by(username="advisor1").first() or create_user("advisor1", "faculty_advisor", "Advisor@Practicum1")


@pytest.fixture
def regular_user(app):
    with app.app_context():
        return create_user("regular_user", "student", "Student@Practicum1")


@pytest.fixture
def db_session(app):
    with app.app_context():
        yield db.session


@pytest.fixture
def auth_client(client, admin_user):
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    return client


def do_reauth(client, password="Admin@Practicum1", next_url="/dashboard"):
    """Perform a real POST /reauth to confirm whatever action is currently pending.

    Call this after a protected endpoint has redirected to /reauth (which stores
    the required action name in the session).  The password must match the
    currently-logged-in user.
    """
    client.post(
        "/reauth",
        data={"password": password, "next_url": next_url},
        follow_redirects=False,
    )


@pytest.fixture
def seeded_assessment(app):
    with app.app_context():
        admin = User.query.filter_by(username="admin").first() or create_user("admin", "dept_admin")
        advisor = User.query.filter_by(username="advisor1").first() or create_user("advisor1", "faculty_advisor", "Advisor@Practicum1")
        mentor = User.query.filter_by(username="mentor1").first() or create_user("mentor1", "corporate_mentor", "Mentor@Practicum1")
        student = User.query.filter_by(username="student1").first() or create_user("student1", "student", "Student@Practicum1")
        student2 = User.query.filter_by(username="student2").first() or create_user("student2", "student", "Student@Practicum1")

        school = School(name="Test School", code="TS", is_active=True)
        db.session.add(school)
        db.session.flush()
        sub = get_or_create_default_subdepartment(school.id)
        major = Major(name="Test Major", code="TM", school_id=school.id, sub_department_id=sub.id)
        db.session.add(major)
        db.session.flush()
        clazz = Class(name="Class A", year=2026, major_id=major.id)
        db.session.add(clazz)
        db.session.flush()
        cohort = Cohort(name="Cohort A", class_id=clazz.id, internship_term="2026 Spring", is_active=True)
        cohort2 = Cohort(name="Cohort B", class_id=clazz.id, internship_term="2026 Spring", is_active=True)
        db.session.add_all([cohort, cohort2])
        db.session.flush()

        db.session.add_all(
            [
                CohortMember(cohort_id=cohort.id, user_id=advisor.id, role_in_cohort="faculty_advisor"),
                CohortMember(cohort_id=cohort.id, user_id=mentor.id, role_in_cohort="corporate_mentor"),
                CohortMember(cohort_id=cohort.id, user_id=student.id, role_in_cohort="student"),
                CohortMember(cohort_id=cohort2.id, user_id=student2.id, role_in_cohort="student"),
            ]
        )

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        paper = Paper(
            title="Paper 1",
            cohort_id=cohort.id,
            creator_id=admin.id,
            status="published",
            time_limit_min=45,
            max_attempts=2,
            total_score=100,
            available_from=now - timedelta(hours=1),
            available_until=now + timedelta(hours=2),
            randomize=False,
            shuffle_options=True,
        )
        paper2 = Paper(
            title="Paper 2",
            cohort_id=cohort2.id,
            creator_id=admin.id,
            status="published",
            time_limit_min=45,
            max_attempts=2,
            total_score=100,
            available_from=now - timedelta(hours=1),
            available_until=now + timedelta(hours=2),
            randomize=False,
            shuffle_options=True,
        )
        db.session.add_all([paper, paper2])
        db.session.flush()

        q1 = Question(
            creator_id=admin.id,
            school_id=school.id,
            question_type="single_choice",
            stem="Single",
            options='[{"key":"A","text":"A"},{"key":"B","text":"B"}]',
            correct_answer="A",
            score_points=2,
            is_active=True,
        )
        q2 = Question(
            creator_id=admin.id,
            school_id=school.id,
            question_type="multiple_choice",
            stem="Multiple",
            options='[{"key":"A","text":"A"},{"key":"B","text":"B"},{"key":"C","text":"C"}]',
            correct_answer='["A","C"]',
            score_points=3,
            is_active=True,
        )
        q3 = Question(
            creator_id=admin.id,
            school_id=school.id,
            question_type="true_false",
            stem="True False",
            options='[{"key":"True","text":"True"},{"key":"False","text":"False"}]',
            correct_answer="True",
            score_points=1,
            is_active=True,
        )
        q4 = Question(
            creator_id=admin.id,
            school_id=school.id,
            question_type="fill_in",
            stem="Fill",
            correct_answer="hello",
            score_points=2,
            is_active=True,
        )
        q5 = Question(
            creator_id=admin.id,
            school_id=school.id,
            question_type="short_answer",
            stem="Short",
            correct_answer=None,
            score_points=5,
            is_active=True,
        )
        db.session.add_all([q1, q2, q3, q4, q5])
        db.session.flush()

        for idx, q in enumerate([q1, q2, q3, q4, q5]):
            db.session.add(PaperQuestion(paper_id=paper.id, question_id=q.id, order_index=idx, score_points=q.score_points))

        db.session.commit()

        return {
            "admin_id": admin.id,
            "advisor_id": advisor.id,
            "mentor_id": mentor.id,
            "student_id": student.id,
            "student2_id": student2.id,
            "cohort_id": cohort.id,
            "cohort2_id": cohort2.id,
            "paper_id": paper.id,
            "paper2_id": paper2.id,
            "question_ids": [q1.id, q2.id, q3.id, q4.id, q5.id],
        }


@pytest.fixture
def seeded_assignment(app, seeded_assessment):
    with app.app_context():
        assignment = Assignment(
            title="Weekly Reflection",
            description="Write your practicum reflection.",
            cohort_id=seeded_assessment["cohort_id"],
            creator_id=seeded_assessment["admin_id"],
            status="published",
            due_date=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=3),
            max_score=100.0,
        )
        assignment_other = Assignment(
            title="Other Cohort Task",
            description="Cohort B assignment",
            cohort_id=seeded_assessment["cohort2_id"],
            creator_id=seeded_assessment["admin_id"],
            status="published",
            due_date=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=2),
            max_score=100.0,
        )
        db.session.add_all([assignment, assignment_other])
        db.session.flush()

        submission = AssignmentSubmission(
            assignment_id=assignment.id,
            student_id=seeded_assessment["student_id"],
            content="Initial draft",
            status="draft",
        )
        db.session.add(submission)
        db.session.commit()

        return {
            "assignment_id": assignment.id,
            "other_assignment_id": assignment_other.id,
            "submission_id": submission.id,
            "student_id": seeded_assessment["student_id"],
            "advisor_id": seeded_assessment["advisor_id"],
            "cohort_id": seeded_assessment["cohort_id"],
            "cohort2_id": seeded_assessment["cohort2_id"],
            "student2_id": seeded_assessment["student2_id"],
        }
