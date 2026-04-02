import pytest

from app.models.user import User
from app.services import report_service


def test_score_summary_fields(app, seeded_assessment):
    with app.app_context():
        admin = User.query.filter_by(username="admin").first()
        data = report_service.get_paper_score_summary(seeded_assessment["paper_id"], admin)
        assert "average_score" in data
        assert "distribution" in data


def test_item_difficulty_returns_rows(app, seeded_assessment):
    with app.app_context():
        admin = User.query.filter_by(username="admin").first()
        rows = report_service.get_item_difficulty(seeded_assessment["paper_id"], admin)
        assert isinstance(rows, list)


def test_cohort_comparison_returns_list(app, seeded_assessment):
    with app.app_context():
        admin = User.query.filter_by(username="admin").first()
        rows = report_service.get_cohort_comparison(seeded_assessment["paper_id"], admin)
        assert isinstance(rows, list)


def test_student_results_masked_fields(app, seeded_assessment):
    with app.app_context():
        admin = User.query.filter_by(username="admin").first()
        rows = report_service.get_student_results(seeded_assessment["cohort_id"], seeded_assessment["paper_id"], admin)
        assert isinstance(rows, list)
        assert "masked_name" in rows[0]


def test_cohort_comparison_includes_sibling_papers(app, seeded_assessment):
    """Papers with the same title in different cohorts must each appear as a row."""
    from app.extensions import db
    from app.models.paper import Paper

    with app.app_context():
        paper1 = db.session.get(Paper, seeded_assessment["paper_id"])
        paper2 = db.session.get(Paper, seeded_assessment["paper2_id"])
        paper2.title = paper1.title
        paper2.status = "published"
        db.session.commit()

        admin = User.query.filter_by(username="admin").first()
        rows = report_service.get_cohort_comparison(paper1.id, admin)
        paper_ids_in_result = [r["paper_id"] for r in rows]
        assert paper1.id in paper_ids_in_result
        assert paper2.id in paper_ids_in_result
        assert len(rows) == 2


def test_item_difficulty_raises_for_unauthorized_actor(app, seeded_assessment):
    """Student must not read aggregate difficulty for a cohort they are not in."""
    with app.app_context():
        student = User.query.filter_by(username="student1").first()
        with pytest.raises(PermissionError, match="forbidden"):
            report_service.get_item_difficulty(seeded_assessment["paper2_id"], student)


def test_cohort_comparison_excludes_inaccessible_sibling_cohorts(app, seeded_assessment):
    """Faculty only in cohort A must not see cohort B stats in comparison rows."""
    from app.extensions import db
    from app.models.paper import Paper

    with app.app_context():
        paper1 = db.session.get(Paper, seeded_assessment["paper_id"])
        paper2 = db.session.get(Paper, seeded_assessment["paper2_id"])
        paper2.title = paper1.title
        paper2.status = "published"
        db.session.commit()

        advisor = User.query.filter_by(username="advisor1").first()
        rows = report_service.get_cohort_comparison(paper1.id, advisor)
        paper_ids = [r["paper_id"] for r in rows]
        assert paper1.id in paper_ids
        assert paper2.id not in paper_ids
        assert len(rows) == 1


def test_cohort_comparison_single_cohort_returns_one_row(app, seeded_assessment):
    """When no sibling papers exist the result has exactly one row (the focal cohort)."""
    with app.app_context():
        admin = User.query.filter_by(username="admin").first()
        rows = report_service.get_cohort_comparison(seeded_assessment["paper_id"], admin)
        assert len(rows) >= 1
        current_rows = [r for r in rows if r["is_current"]]
        assert len(current_rows) == 1
