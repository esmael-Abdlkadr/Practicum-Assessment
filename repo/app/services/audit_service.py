import csv
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from io import StringIO

from flask import has_request_context, request, session

from app.extensions import db
from app.models.audit_log import AuditLog

AUDIT_RETENTION_DAYS = int(os.environ.get("AUDIT_RETENTION_DAYS", 1095))


def get_device_fingerprint(req) -> str:
    user_agent = req.headers.get("User-Agent", "")
    accept_language = req.headers.get("Accept-Language", "")
    platform = req.headers.get("Sec-CH-UA-Platform", "") or req.headers.get("X-Platform", "")
    raw = f"{user_agent}|{accept_language}|{platform}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _json_text(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, default=str)


def _request_ip() -> str:
    if not has_request_context():
        return "system"
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def log(action, resource_type=None, resource_id=None, old_value=None, new_value=None, extra=None):
    actor_id = session.get("user_id") if has_request_context() else None
    actor_username = None

    if actor_id:
        from app.models.user import User

        u = db.session.get(User, actor_id)
        if u:
            actor_username = u.username
    elif has_request_context() and session.get("pending_username"):
        actor_username = session.get("pending_username")

    entry = AuditLog(
        actor_id=actor_id,
        actor_username=actor_username,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        old_value=_json_text(old_value),
        new_value=_json_text(new_value),
        ip_address=_request_ip(),
        device_fingerprint=get_device_fingerprint(request) if has_request_context() else "system",
        extra=_json_text(extra),
    )
    db.session.add(entry)
    db.session.commit()
    return entry


def search_logs(filters: dict, page: int, per_page: int):
    query = AuditLog.query

    actor = (filters.get("actor") or "").strip()
    action = (filters.get("action") or "").strip()
    resource_type = (filters.get("resource_type") or "").strip()
    start_date = (filters.get("start_date") or "").strip()
    end_date = (filters.get("end_date") or "").strip()

    if actor:
        query = query.filter(AuditLog.actor_username.ilike(f"%{actor}%"))
    if action:
        query = query.filter(AuditLog.action == action)
    if resource_type:
        query = query.filter(AuditLog.resource_type == resource_type)
    if start_date:
        query = query.filter(AuditLog.created_at >= datetime.fromisoformat(start_date))
    if end_date:
        query = query.filter(AuditLog.created_at <= datetime.fromisoformat(end_date))

    return query.order_by(AuditLog.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)


def detect_anomalies(user_id: int) -> list[str]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    anomalies: list[str] = []

    failed_1h = (
        AuditLog.query.filter(
            AuditLog.actor_id == user_id,
            AuditLog.action.in_(["LOGIN_FAILED", "LOGIN_FAILED_MFA"]),
            AuditLog.created_at >= now - timedelta(hours=1),
        ).count()
    )
    if failed_1h > 5:
        anomalies.append("More than 5 failed logins in 1 hour")

    latest_success = (
        AuditLog.query.filter(AuditLog.actor_id == user_id, AuditLog.action == "LOGIN_SUCCESS")
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    if latest_success:
        seen_count = (
            AuditLog.query.filter(
                AuditLog.actor_id == user_id,
                AuditLog.action == "LOGIN_SUCCESS",
                AuditLog.device_fingerprint == latest_success.device_fingerprint,
                AuditLog.created_at >= now - timedelta(days=30),
            ).count()
        )
        if seen_count == 1:
            anomalies.append("Login from a new device fingerprint in last 30 days")

        hour = latest_success.created_at.hour
        if hour < 6 or hour >= 23:
            anomalies.append("Login at unusual hour")

    ip_count = (
        db.session.query(AuditLog.ip_address)
        .filter(
            AuditLog.actor_id == user_id,
            AuditLog.action == "LOGIN_SUCCESS",
            AuditLog.created_at >= now - timedelta(hours=24),
        )
        .distinct()
        .count()
    )
    if ip_count > 3:
        anomalies.append("More than 3 different IP addresses in 24 hours")

    return anomalies


def evaluate_user_anomalies(user_id: int, username: str) -> int:
    """Run anomaly detection for a single user and persist new flags.

    Called automatically on login events.  Only checks the one user (no
    full-table scan) and de-duplicates against existing unreviewed flags.
    Returns the number of new flags created.
    """
    from app.models.anomaly_flag import AnomalyFlag

    anomaly_messages = detect_anomalies(user_id)
    created = 0
    for message in anomaly_messages:
        exists = AnomalyFlag.query.filter_by(
            user_id=user_id, anomaly_type=message, reviewed=False
        ).first()
        if not exists:
            flag = AnomalyFlag(
                user_id=user_id,
                username=username,
                anomaly_type=message,
                detected_at=datetime.now(timezone.utc).replace(tzinfo=None),
                reviewed=False,
            )
            db.session.add(flag)
            created += 1
    if created:
        db.session.commit()
    return created


def export_logs_csv(pagination) -> str:
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "id",
        "timestamp",
        "actor_username",
        "action",
        "resource_type",
        "resource_id",
        "ip_address",
        "device_fingerprint",
        "extra",
    ])

    for row in pagination.items:
        writer.writerow(
            [
                row.id,
                row.created_at.isoformat() if row.created_at else "",
                row.actor_username or "",
                row.action,
                row.resource_type or "",
                row.resource_id or "",
                row.ip_address or "",
                row.device_fingerprint or "",
                row.extra or "",
            ]
        )

    return buffer.getvalue()


def _archive_logs(logs: list[AuditLog], archive_dir: str | None = None) -> str | None:
    """Write *logs* to a timestamped CSV archive file.

    Returns the archive file path, or ``None`` if no logs to archive.
    """
    if not logs:
        return None

    if archive_dir is None:
        archive_dir = os.environ.get("AUDIT_ARCHIVE_DIR", "data/audit_archive")

    from pathlib import Path

    path = Path(archive_dir)
    path.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filepath = path / f"audit_archive_{stamp}.csv"

    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "id", "timestamp", "actor_id", "actor_username", "action",
        "resource_type", "resource_id", "old_value", "new_value",
        "ip_address", "device_fingerprint", "extra",
    ])
    for row in logs:
        writer.writerow([
            row.id,
            row.created_at.isoformat() if row.created_at else "",
            row.actor_id or "",
            row.actor_username or "",
            row.action,
            row.resource_type or "",
            row.resource_id or "",
            row.old_value or "",
            row.new_value or "",
            row.ip_address or "",
            row.device_fingerprint or "",
            row.extra or "",
        ])

    filepath.write_text(buffer.getvalue(), encoding="utf-8")
    return str(filepath)


def purge_old_logs() -> int:
    """Archive then delete audit logs older than AUDIT_RETENTION_DAYS.

    Append-only semantics are enforced within the retention window by the
    ORM-level event listeners on AuditLog (before_update / before_delete).
    Beyond the retention window, logs are first archived to CSV, then bulk-
    deleted via a raw query that bypasses the ORM listeners.

    Returns count of purged rows.
    """
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=AUDIT_RETENTION_DAYS)
    expired = AuditLog.query.filter(AuditLog.created_at < cutoff).all()
    if not expired:
        return 0

    # Archive before delete.
    _archive_logs(expired)

    count = len(expired)
    expired_ids = [row.id for row in expired]

    # Expunge rows from session so ORM before_delete listener is not triggered,
    # then bulk delete via raw SQL.
    for row in expired:
        db.session.expunge(row)

    from sqlalchemy import text

    placeholders = ", ".join(str(int(i)) for i in expired_ids)
    db.session.execute(text(f"DELETE FROM audit_logs WHERE id IN ({placeholders})"))
    db.session.commit()
    return count
