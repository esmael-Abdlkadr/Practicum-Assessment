import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.extensions import db
from app.models.audit_log import AuditLog
from app.services import audit_service


def test_purge_old_logs_deletes_only_expired(app):
    with app.app_context():
        old_row = AuditLog(action="OLD", created_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1200))
        keep_row = AuditLog(action="NEW", created_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=5))
        db.session.add_all([old_row, keep_row])
        db.session.commit()

        deleted = audit_service.purge_old_logs()

        assert deleted == 1
        assert AuditLog.query.filter_by(action="OLD").count() == 0
        assert AuditLog.query.filter_by(action="NEW").count() == 1


def test_purge_archives_before_delete(app, tmp_path, monkeypatch):
    """purge_old_logs must create a CSV archive file before deleting rows."""
    monkeypatch.setenv("AUDIT_ARCHIVE_DIR", str(tmp_path / "archive"))
    with app.app_context():
        old_row = AuditLog(
            action="ARCHIVE_ME",
            actor_username="test_actor",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1200),
        )
        db.session.add(old_row)
        db.session.commit()

        deleted = audit_service.purge_old_logs()
        assert deleted == 1

        archive_dir = tmp_path / "archive"
        assert archive_dir.exists()
        csv_files = list(archive_dir.glob("audit_archive_*.csv"))
        assert len(csv_files) >= 1
        content = csv_files[0].read_text()
        assert "ARCHIVE_ME" in content
        assert "test_actor" in content


def test_purge_no_expired_returns_zero(app):
    """If no logs are expired, purge returns 0 and does nothing."""
    with app.app_context():
        fresh = AuditLog(action="FRESH", created_at=datetime.now(timezone.utc).replace(tzinfo=None))
        db.session.add(fresh)
        db.session.commit()
        assert audit_service.purge_old_logs() == 0
        assert AuditLog.query.filter_by(action="FRESH").count() == 1


def test_append_only_within_retention_window(app):
    """Logs within the retention window cannot be updated or deleted via ORM."""
    with app.app_context():
        log = AuditLog(
            action="RECENT_LOG",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=5),
        )
        db.session.add(log)
        db.session.commit()

        # ORM update must raise
        log.action = "TAMPERED"
        import sqlalchemy.exc
        with pytest.raises((PermissionError, sqlalchemy.exc.InvalidRequestError)):
            db.session.flush()
        db.session.rollback()

        # ORM delete must raise
        fetched = db.session.get(AuditLog, log.id)
        with pytest.raises(PermissionError):
            fetched.delete()


def test_audit_log_immut_update_raises_permission_error(app):
    """Direct ORM update of an AuditLog must raise PermissionError."""
    with app.app_context():
        log = AuditLog(action="IMMUTABLE_TEST")
        db.session.add(log)
        db.session.commit()
        log_id = log.id

        fetched = db.session.get(AuditLog, log_id)

        with pytest.raises(PermissionError):
            fetched.update(action="TAMPERED")


def test_audit_log_immut_delete_raises_permission_error(app):
    """Direct ORM delete of an AuditLog must raise PermissionError."""
    with app.app_context():
        log = AuditLog(action="DELETE_TEST")
        db.session.add(log)
        db.session.commit()
        log_id = log.id
        fetched = db.session.get(AuditLog, log_id)

        with pytest.raises(PermissionError):
            fetched.delete()


def test_audit_log_immut_sqlalchemy_before_update_hook_fires(app):
    """SQLAlchemy before_update event must prevent UPDATE reaching the DB."""
    with app.app_context():
        import sqlalchemy.exc

        log = AuditLog(action="HOOK_TEST")
        db.session.add(log)
        db.session.commit()

        log.action = "MODIFIED"
        with pytest.raises((PermissionError, sqlalchemy.exc.InvalidRequestError)):
            db.session.flush()
        db.session.rollback()
