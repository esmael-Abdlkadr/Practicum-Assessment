from datetime import datetime, timedelta, timezone

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


def test_audit_log_immut_update_raises_permission_error(app):
    """Direct ORM update of an AuditLog must raise PermissionError."""
    with app.app_context():
        log = AuditLog(action="IMMUTABLE_TEST")
        db.session.add(log)
        db.session.commit()
        log_id = log.id

        fetched = db.session.get(AuditLog, log_id)
        import pytest

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
        import pytest

        with pytest.raises(PermissionError):
            fetched.delete()


def test_audit_log_immut_sqlalchemy_before_update_hook_fires(app):
    """SQLAlchemy before_update event must prevent UPDATE reaching the DB."""
    with app.app_context():
        import sqlalchemy.exc
        import pytest

        log = AuditLog(action="HOOK_TEST")
        db.session.add(log)
        db.session.commit()

        log.action = "MODIFIED"
        with pytest.raises((PermissionError, sqlalchemy.exc.InvalidRequestError)):
            db.session.flush()
        db.session.rollback()
