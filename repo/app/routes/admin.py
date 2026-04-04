from datetime import datetime, timezone

from flask import Blueprint, Response, render_template, request

from app.extensions import db
from app.models.anomaly_flag import AnomalyFlag
from app.models.paper import Paper
from app.models.user import User
from app.services import audit_service
from app.services.decorators import login_required, require_role

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _filters_from_request():
    return {
        "actor": request.args.get("actor", ""),
        "action": request.args.get("action", ""),
        "resource_type": request.args.get("resource_type", ""),
        "start_date": request.args.get("start_date", ""),
        "end_date": request.args.get("end_date", ""),
    }


@admin_bp.get("/audit-logs")
@login_required
@require_role("dept_admin")
def audit_logs_page():
    page = int(request.args.get("page", 1))
    filters = _filters_from_request()
    pagination = audit_service.search_logs(filters, page=page, per_page=20)
    return render_template("admin/audit_logs.html", pagination=pagination, filters=filters)


@admin_bp.get("/audit-logs/search")
@login_required
@require_role("dept_admin")
def audit_logs_search():
    page = int(request.args.get("page", 1))
    filters = _filters_from_request()
    pagination = audit_service.search_logs(filters, page=page, per_page=20)
    return render_template("admin/_audit_table.html", pagination=pagination, filters=filters)


@admin_bp.get("/audit-logs/export")
@login_required
@require_role("dept_admin")
def audit_logs_export():
    filters = _filters_from_request()
    pagination = audit_service.search_logs(filters, page=1, per_page=10000)
    content = audit_service.export_logs_csv(pagination)
    return Response(
        content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_logs.csv"},
    )


@admin_bp.get("/anomalies")
@login_required
@require_role("dept_admin")
def anomalies_page():
    """Read-only view — returns existing anomaly flags without any side effects."""
    rows = AnomalyFlag.query.order_by(AnomalyFlag.detected_at.desc()).all()
    return render_template("admin/anomalies.html", anomalies=rows)


@admin_bp.post("/anomalies/scan")
@login_required
@require_role("dept_admin")
def anomalies_scan():
    """Explicit trigger: detect anomalies, persist new flags, and emit audit events."""
    from app.services.session_service import get_current_user as _get_actor

    actor = _get_actor()
    actor_id = actor.id if actor else None
    users = User.query.all()
    created = 0

    for user in users:
        anomaly_messages = audit_service.detect_anomalies(user.id)
        for message in anomaly_messages:
            exists = AnomalyFlag.query.filter_by(user_id=user.id, anomaly_type=message, reviewed=False).first()
            if not exists:
                flag = AnomalyFlag(
                    user_id=user.id,
                    username=user.username,
                    anomaly_type=message,
                    detected_at=datetime.now(timezone.utc).replace(tzinfo=None),
                    reviewed=False,
                )
                db.session.add(flag)
                created += 1

    db.session.commit()

    # Emit one audit event per new flag (flush individually for traceability)
    if created:
        audit_service.log(
            action="ANOMALY_FLAGS_CREATED",
            resource_type="anomaly_flag",
            resource_id=None,
            extra={"count": created, "actor_id": actor_id},
        )

    rows = AnomalyFlag.query.order_by(AnomalyFlag.detected_at.desc()).all()
    return render_template("admin/_anomalies_table.html", anomalies=rows, scan_message=f"{created} new flag(s) created.")


@admin_bp.post("/anomalies/<int:flag_id>/review")
@login_required
@require_role("dept_admin")
def mark_anomaly_reviewed(flag_id: int):
    flag = AnomalyFlag.query.get_or_404(flag_id)
    flag.reviewed = True
    db.session.add(flag)
    db.session.commit()
    audit_service.log(
        action="ANOMALY_FLAG_REVIEWED",
        resource_type="anomaly_flag",
        resource_id=flag_id,
    )
    status = "reviewed" if flag.reviewed else "unreviewed"
    return f"<span class='badge text-bg-success'>{status}</span>"


@admin_bp.get("/dashboard")
@login_required
@require_role("dept_admin")
def admin_dashboard():
    active_users = User.query.filter(User.is_active.is_(True)).count()
    locked_accounts = User.query.filter(User.locked_until.is_not(None)).count()
    recent_audit = audit_service.search_logs({}, page=1, per_page=10).items
    papers_active = Paper.query.filter(Paper.status == "published").count()
    papers_draft = Paper.query.filter(Paper.status == "draft").count()
    papers_closed = Paper.query.filter(Paper.status == "closed").count()
    anomaly_unreviewed = AnomalyFlag.query.filter(AnomalyFlag.reviewed.is_(False)).count()

    db_size = 0
    try:
        import os
        from flask import current_app

        db_uri = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
        if db_uri.startswith("sqlite:////"):
            db_path = db_uri.replace("sqlite:////", "/", 1)
            db_size = os.path.getsize(db_path)
        elif db_uri.startswith("sqlite:///") and db_uri != "sqlite:///:memory:":
            db_path = db_uri.replace("sqlite:///", "", 1)
            db_size = os.path.getsize(db_path)
    except Exception:
        db_size = 0

    return render_template(
        "admin/dashboard.html",
        active_users=active_users,
        locked_accounts=locked_accounts,
        recent_audit=recent_audit,
        papers_active=papers_active,
        papers_draft=papers_draft,
        papers_closed=papers_closed,
        anomaly_unreviewed=anomaly_unreviewed,
        db_size=db_size,
    )
