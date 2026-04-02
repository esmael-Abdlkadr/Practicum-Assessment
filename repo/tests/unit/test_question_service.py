import pytest

from app import create_app
from app.extensions import db
from app.services import question_service
from tests.conftest import create_user


@pytest.fixture
def app_ctx(app):
    with app.app_context():
        yield app


def test_single_choice_valid_passes(app_ctx, seeded_assessment):
    with app_ctx.app_context():
        admin_id = seeded_assessment["admin_id"]
        school_id = 1
        q = question_service.create_question(
            creator_id=admin_id,
            school_id=school_id,
            question_type="single_choice",
            stem="Which is correct?",
            options=[{"key": "A", "text": "Yes"}, {"key": "B", "text": "No"}],
            correct_answer="A",
            score_points=2,
            tags=[],
        )
        assert q.id is not None


def test_single_choice_invalid_answer_raises(app_ctx, seeded_assessment):
    with app_ctx.app_context():
        import pytest as _pytest

        with _pytest.raises((ValueError, Exception)):
            question_service.create_question(
                creator_id=seeded_assessment["admin_id"],
                school_id=1,
                question_type="single_choice",
                stem="Q",
                options=[{"key": "A", "text": "Yes"}],
                correct_answer="Z",
                score_points=1,
                tags=[],
            )


def test_multiple_choice_valid_passes(app_ctx, seeded_assessment):
    with app_ctx.app_context():
        q = question_service.create_question(
            creator_id=seeded_assessment["admin_id"],
            school_id=1,
            question_type="multiple_choice",
            stem="Select all correct",
            options=[
                {"key": "A", "text": "A"},
                {"key": "B", "text": "B"},
                {"key": "C", "text": "C"},
            ],
            correct_answer=["A", "C"],
            score_points=3,
            tags=[],
        )
        assert q.id is not None


def test_true_false_invalid_answer_raises(app_ctx, seeded_assessment):
    with app_ctx.app_context():
        import pytest as _pytest

        with _pytest.raises((ValueError, Exception)):
            question_service.create_question(
                creator_id=seeded_assessment["admin_id"],
                school_id=1,
                question_type="true_false",
                stem="Is this correct?",
                options=[{"key": "True", "text": "True"}, {"key": "False", "text": "False"}],
                correct_answer="Maybe",
                score_points=1,
                tags=[],
            )


def test_fill_in_requires_correct_answer(app_ctx, seeded_assessment):
    with app_ctx.app_context():
        import pytest as _pytest

        with _pytest.raises((ValueError, Exception)):
            question_service.create_question(
                creator_id=seeded_assessment["admin_id"],
                school_id=1,
                question_type="fill_in",
                stem="The answer is ___",
                options=None,
                correct_answer=None,
                score_points=2,
                tags=[],
            )


def test_short_answer_allows_no_correct_answer(app_ctx, seeded_assessment):
    with app_ctx.app_context():
        q = question_service.create_question(
            creator_id=seeded_assessment["admin_id"],
            school_id=1,
            question_type="short_answer",
            stem="Describe the process",
            options=None,
            correct_answer=None,
            score_points=5,
            tags=[],
        )
        assert q.id is not None


def test_invalid_question_type_raises(app_ctx, seeded_assessment):
    with app_ctx.app_context():
        import pytest as _pytest

        with _pytest.raises((ValueError, Exception)):
            question_service.create_question(
                creator_id=seeded_assessment["admin_id"],
                school_id=1,
                question_type="essay",
                stem="Write something",
                options=None,
                correct_answer=None,
                score_points=5,
                tags=[],
            )
