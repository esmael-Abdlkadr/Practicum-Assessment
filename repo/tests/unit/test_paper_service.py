import json

import pytest

from app.extensions import db
from app.models.paper import Paper
from app.models.paper import PaperQuestion
from app.models.user import User
from app.services import paper_service


def test_publish_paper_with_no_questions_validation_error(app, seeded_assessment):
    with app.app_context():
        admin = User.query.filter_by(username="admin").first()
        paper = db.session.get(Paper, seeded_assessment["paper2_id"])
        with pytest.raises(ValueError):
            paper_service.publish_paper(paper.id, admin)


def test_publish_paper_randomize_draw_exceeds_pool_error(app, seeded_assessment):
    with app.app_context():
        admin = User.query.filter_by(username="admin").first()
        paper = db.session.get(Paper, seeded_assessment["paper_id"])
        paper.randomize = True
        paper.draw_count = 999
        paper.draw_tags = json.dumps(["not-existing-tag"])
        db.session.add(paper)
        db.session.commit()
        with pytest.raises(ValueError):
            paper_service.publish_paper(paper.id, admin)


def test_get_questions_for_student_deterministic_same_student(app, seeded_assessment):
    with app.app_context():
        student = User.query.filter_by(username="student1").first()
        paper = db.session.get(Paper, seeded_assessment["paper_id"])
        paper.randomize = True
        paper.draw_count = 2
        paper.draw_tags = json.dumps([])
        db.session.add(paper)
        db.session.commit()

        ids1 = [q.id for q in paper_service.get_questions_for_student(paper, student.id)]
        ids2 = [q.id for q in paper_service.get_questions_for_student(paper, student.id)]
        assert ids1 == ids2


def test_get_questions_for_student_different_students_diff_order(app, seeded_assessment):
    with app.app_context():
        s1 = User.query.filter_by(username="student1").first()
        s2 = User.query.filter_by(username="student2").first()
        paper = db.session.get(Paper, seeded_assessment["paper_id"])
        paper.randomize = False
        paper.shuffle_options = True
        db.session.add(paper)
        db.session.commit()

        qset1 = [q.id for q in paper_service.get_questions_for_student(paper, s1.id)]
        qset2 = [q.id for q in paper_service.get_questions_for_student(paper, s2.id)]
        assert qset1 == qset2


def test_shuffle_options_does_not_mutate_persisted_question(app, seeded_assessment):
    """Regression: get_questions_for_student() must not dirty the ORM Question entity.

    Previously q.options was mutated in-place on the ORM object, allowing SQLAlchemy
    to flush the shuffled order back to the database, corrupting the view for later students.
    """
    from app.models.question import Question

    with app.app_context():
        student = User.query.filter_by(username="student1").first()
        paper = db.session.get(Paper, seeded_assessment["paper_id"])
        paper.shuffle_options = True
        db.session.add(paper)
        db.session.commit()

        # capture the original stored options for every question with options
        before = {
            q.id: q.options
            for q in Question.query.all()
            if q.options
        }

        # call the function — this should NOT write back to the DB
        views = paper_service.get_questions_for_student(paper, student.id)

        # force any pending flushes
        db.session.flush()

        after = {
            q.id: q.options
            for q in Question.query.all()
            if q.options
        }

        assert before == after, "get_questions_for_student() must not mutate persisted Question.options"

        # also verify the returned views are SimpleNamespace objects (not ORM rows)
        from types import SimpleNamespace
        for view in views:
            assert isinstance(view, SimpleNamespace), "Views must be detached SimpleNamespace objects"


def test_reorder_questions_updates_order_index(app, seeded_assessment):
    with app.app_context():
        paper = db.session.get(Paper, seeded_assessment["paper_id"])
        links = PaperQuestion.query.filter_by(paper_id=paper.id).order_by(PaperQuestion.order_index.asc()).all()
        ordered = [l.question_id for l in reversed(links)]
        paper_service.reorder_questions(paper.id, ordered)
        updated = PaperQuestion.query.filter_by(paper_id=paper.id).order_by(PaperQuestion.order_index.asc()).all()
        assert [u.question_id for u in updated] == ordered
