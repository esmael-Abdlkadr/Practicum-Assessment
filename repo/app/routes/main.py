from flask import Blueprint, Response, current_app, redirect, request as _req, url_for
from sqlalchemy import text

from app.extensions import csrf, db

main_bp = Blueprint("main", __name__)
ALLOWED_LOG_KEYS = {"level", "category", "message", "detail", "url", "ts"}
MAX_PAYLOAD_BYTES = 4096


@main_bp.get("/")
def home():
    return redirect(url_for("auth.login_page"))


@main_bp.get("/health")
@csrf.exempt
def health():
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        return Response(
            '{"status":"error","db":"disconnected","version":"1.0.0"}',
            status=500,
            mimetype="application/json",
        )

    return Response(
        '{"status":"ok","db":"connected","version":"1.0.0"}',
        mimetype="application/json",
    )


@main_bp.post("/client-error-log")
@csrf.exempt
def client_error_log():
    """Receives client-side JS/HTMX error beacons and writes to server log."""
    try:
        import json as _json

        raw = _req.get_data(as_text=False)
        if len(raw) > MAX_PAYLOAD_BYTES:
            return "", 413
        payload = raw.decode("utf-8", errors="replace")
        entry = _json.loads(payload) if payload.strip() else {}
        safe = {
            k: str(v)[:512]
            for k, v in entry.items()
            if k in ALLOWED_LOG_KEYS
        }
        current_app.logger.warning(
            "CLIENT_ERROR level=%s category=%s message=%s detail=%s",
            safe.get("level", "?"),
            safe.get("category", "?"),
            safe.get("message", "?"),
            safe.get("detail", ""),
        )
    except Exception:
        pass
    return "", 204
