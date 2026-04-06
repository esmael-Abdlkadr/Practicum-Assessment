import os
import secrets
from datetime import timedelta
from pathlib import Path

DEFAULT_DATABASE_URL = "sqlite:///data/practicum.db"

# Known-weak patterns that must never be used outside tests.
_INSECURE_KEY_PATTERNS = (
    "practicum-dev-secret-key-change-in-production",
    "change-me-in-production",
    "change-me",
    "secret",
)


def _get_or_generate_secret_key() -> str:
    """Return a safe SECRET_KEY for non-test runtime.

    Priority:
    1. ``SECRET_KEY`` environment variable (must not be a known-weak value).
    2. A per-install random key persisted to ``data/.secret_key``.
    3. Generates a new random key and persists it.
    """
    env_key = os.environ.get("SECRET_KEY", "").strip()

    if env_key:
        low = env_key.lower()
        if any(pat in low for pat in _INSECURE_KEY_PATTERNS):
            # Fall through to auto-generated key rather than using weak value.
            pass
        elif len(env_key) < 16:
            pass  # Too short — fall through.
        else:
            return env_key

    # Auto-generate and persist a per-install secret.
    key_path = Path(os.environ.get("SECRET_KEY_FILE", "data/.secret_key"))
    if not key_path.is_absolute():
        key_path = Path(__file__).resolve().parent.parent / key_path
    try:
        existing = key_path.read_text().strip()
        if len(existing) >= 32:
            return existing
    except (FileNotFoundError, PermissionError, OSError):
        pass

    new_key = secrets.token_hex(32)
    try:
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_text(new_key)
        key_path.chmod(0o600)
    except OSError:
        pass  # Ephemeral environments (e.g. CI): use in-memory key.
    return new_key


class Config:
    SECRET_KEY = _get_or_generate_secret_key()
    WTF_CSRF_SECRET_KEY = os.environ.get("WTF_CSRF_SECRET_KEY", SECRET_KEY)
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_TYPE = "filesystem"
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = os.environ.get("SECRET_KEY", "testing-secret-key")
    WTF_CSRF_SECRET_KEY = os.environ.get("WTF_CSRF_SECRET_KEY", SECRET_KEY)
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False


class ProductionConfig(Config):
    DEBUG = False


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
