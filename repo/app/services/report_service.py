import csv
from datetime import datetime, timezone
from io import BytesIO, StringIO

from flask import send_file

from app.extensions import db
from app.models.assignment import CohortMember
from app.models.attempt import Attempt
from app.models.grading import GradingResult
from app.models.org import Cohort
from app.models.paper import Paper, PaperQuestion
from app.models.question import Question
from app.models.user import User
from app.services import encryption_service, rbac_service


def get_paper_score_summary(paper_id: int, actor, effective_role: str | None = None):
    paper = db.session.get(Paper, paper_id)
    if not paper:
        raise PermissionError("not_found")
    if not rbac_service.can_access_cohort(actor, paper.cohort_id, effective_role=effective_role):
        raise PermissionError("forbidden")

    assigned = CohortMember.query.filter_by(cohort_id=paper.cohort_id, role_in_cohort="student").count()
    attempts = Attempt.query.filter_by(paper_id=paper_id).all()
    attempted = len(attempts)
    submitted = len([a for a in attempts if a.status in ["submitted", "finalized", "timed_out"]])

    scores = [float(a.score or 0.0) for a in attempts if a.score is not None]
    avg_score = sum(scores) / len(scores) if scores else 0.0
    highest = max(scores) if scores else 0.0
    lowest = min(scores) if scores else 0.0
    pass_threshold = float(paper.total_score or 100.0) * 0.6
    pass_rate = (len([s for s in scores if s >= pass_threshold]) / len(scores)) if scores else 0.0

    distribution = {f"{i}-{i+10}": 0 for i in range(0, 100, 10)}
    for s in scores:
        bucket = min(int(s // 10) * 10, 90)
        distribution[f"{bucket}-{bucket+10}"] += 1

    return {
        "paper": paper,
        "total_assigned": assigned,
        "attempted": attempted,
        "submitted": submitted,
        "average_score": round(avg_score, 2),
        "highest_score": highest,
        "lowest_score": lowest,
        "pass_rate": round(pass_rate, 4),
        "distribution": distribution,
    }


def get_item_difficulty(paper_id: int, actor, effective_role: str | None = None):
    paper = db.session.get(Paper, paper_id)
    if not paper:
        raise PermissionError("not_found")
    if not rbac_service.can_access_cohort(actor, paper.cohort_id, effective_role=effective_role):
        raise PermissionError("forbidden")

    links = PaperQuestion.query.filter_by(paper_id=paper_id).all()
    result = []
    for link in links:
        q = db.session.get(Question, link.question_id)
        if not q:
            continue
        grading_rows = (
            GradingResult.query.join(Attempt, Attempt.id == GradingResult.attempt_id)
            .filter(Attempt.paper_id == paper_id, GradingResult.question_id == q.id)
            .all()
        )
        attempt_count = len(grading_rows)
        correct_count = len([g for g in grading_rows if g.is_correct is True])
        difficulty_index = (correct_count / attempt_count) if attempt_count else 0.0
        flag = ""
        if difficulty_index < 0.3:
            flag = "Very Hard"
        elif difficulty_index > 0.9:
            flag = "Too Easy"
        result.append(
            {
                "question_id": q.id,
                "stem": (q.stem or "")[:60],
                "type": q.question_type,
                "correct_count": correct_count,
                "attempt_count": attempt_count,
                "difficulty_index": difficulty_index,
                "flag": flag,
            }
        )
    return sorted(result, key=lambda x: x["difficulty_index"])


def get_cohort_comparison(paper_id: int, actor, effective_role: str | None = None):
    """Compare the given paper's cohort results against sibling papers
    (same title, different cohorts). Falls back to single-cohort stats when
    no siblings exist."""
    focal_paper = db.session.get(Paper, paper_id)
    if not focal_paper:
        raise PermissionError("not_found")

    if not rbac_service.can_access_cohort(actor, focal_paper.cohort_id, effective_role=effective_role):
        raise PermissionError("forbidden")

    sibling_papers = Paper.query.filter_by(title=focal_paper.title, status="published").all()
    result = []
    for paper in sibling_papers:
        if not rbac_service.can_access_cohort(actor, paper.cohort_id, effective_role=effective_role):
            continue
        cohort = db.session.get(Cohort, paper.cohort_id)
        attempts = Attempt.query.filter_by(paper_id=paper.id).filter(Attempt.status.in_(["submitted", "finalized"])).all()
        scores = [float(a.score or 0.0) for a in attempts if a.score is not None]
        total = len(attempts)
        avg = round(sum(scores) / len(scores), 2) if scores else 0.0
        pass_rate = round(len([s for s in scores if s >= 60]) / len(scores), 4) if scores else 0.0
        result.append(
            {
                "cohort_id": paper.cohort_id,
                "cohort_name": cohort.name if cohort else f"#{paper.cohort_id}",
                "paper_id": paper.id,
                "student_count": total,
                "avg_score": avg,
                "pass_rate": pass_rate,
                "is_current": paper.id == paper_id,
            }
        )
    return sorted(result, key=lambda x: x["avg_score"], reverse=True)


def get_student_results(cohort_id: int, paper_id: int, actor, effective_role: str | None = None):
    if not rbac_service.can_access_cohort(actor, cohort_id, effective_role=effective_role):
        raise PermissionError("forbidden")

    members = CohortMember.query.filter_by(cohort_id=cohort_id, role_in_cohort="student").all()
    out = []
    for m in members:
        user = db.session.get(User, m.user_id)
        if not user:
            continue
        attempt = (
            Attempt.query.filter_by(student_id=user.id, paper_id=paper_id)
            .order_by(Attempt.id.desc())
            .first()
        )
        sid_masked = ""
        if user and user.student_id_enc:
            try:
                sid_masked = encryption_service.mask_student_id(encryption_service.decrypt(user.student_id_enc))
            except Exception:
                sid_masked = ""

        time_taken = None
        grading_status = "not_attempted"
        if attempt:
            if attempt.finalized_at:
                time_taken = int((attempt.finalized_at - attempt.started_at).total_seconds())
            pending = GradingResult.query.filter_by(attempt_id=attempt.id, status="pending").count()
            grading_status = "pending" if pending > 0 else "graded"
        out.append(
            {
                "student_id": user.id if user else None,
                "masked_name": user.username if user else "unknown",
                "masked_student_id": sid_masked,
                "attempt_status": attempt.status if attempt else "not_attempted",
                "score": attempt.score if attempt else None,
                "time_taken": time_taken,
                "grading_status": grading_status,
            }
        )
    return out


def export_to_csv(data: list[dict], filename: str):
    output = StringIO()
    if data:
        fieldnames = list(data[0].keys())
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for row in data:
            writer.writerow(row)
    else:
        output.write("\n")

    bytes_buf = BytesIO(output.getvalue().encode("utf-8"))
    bytes_buf.seek(0)
    stamped = datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y%m%d_%H%M%S")
    return send_file(bytes_buf, mimetype="text/csv", as_attachment=True, download_name=f"{filename}_{stamped}.csv")
