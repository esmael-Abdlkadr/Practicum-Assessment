"""Tests for SECRET_KEY security (F-002)."""
import os
import tempfile

import pytest


def test_testing_config_uses_deterministic_key():
    """TestingConfig must use a deterministic key so tests are reproducible."""
    from app.config import TestingConfig

    assert TestingConfig.SECRET_KEY == "testing-secret-key"


def test_weak_key_rejected_by_generator(monkeypatch, tmp_path):
    """_get_or_generate_secret_key must reject known-weak patterns."""
    monkeypatch.setenv("SECRET_KEY", "practicum-dev-secret-key-change-in-production")
    key_file = tmp_path / ".secret_key"
    monkeypatch.setenv("SECRET_KEY_FILE", str(key_file))
    # Re-import to pick up changed env
    from app.config import _get_or_generate_secret_key

    result = _get_or_generate_secret_key()
    assert result != "practicum-dev-secret-key-change-in-production"
    assert len(result) >= 32


def test_short_key_rejected(monkeypatch, tmp_path):
    """Keys shorter than 16 chars are rejected."""
    monkeypatch.setenv("SECRET_KEY", "short")
    key_file = tmp_path / ".secret_key"
    monkeypatch.setenv("SECRET_KEY_FILE", str(key_file))
    from app.config import _get_or_generate_secret_key

    result = _get_or_generate_secret_key()
    assert result != "short"
    assert len(result) >= 32


def test_strong_env_key_accepted(monkeypatch, tmp_path):
    """A strong env key is used as-is."""
    strong = "a" * 64
    monkeypatch.setenv("SECRET_KEY", strong)
    monkeypatch.setenv("SECRET_KEY_FILE", str(tmp_path / ".secret_key"))
    from app.config import _get_or_generate_secret_key

    assert _get_or_generate_secret_key() == strong


def test_auto_generated_key_persisted(monkeypatch, tmp_path):
    """When no env key, a random key is generated and persisted to file."""
    monkeypatch.setenv("SECRET_KEY", "")
    key_file = tmp_path / ".secret_key"
    monkeypatch.setenv("SECRET_KEY_FILE", str(key_file))
    from app.config import _get_or_generate_secret_key

    key1 = _get_or_generate_secret_key()
    assert len(key1) >= 32
    assert key_file.exists()
    # Second call reads from file — same key
    key2 = _get_or_generate_secret_key()
    assert key1 == key2


def test_config_secret_key_not_default():
    """The non-test Config class must never use the old hardcoded default."""
    from app.config import Config

    assert "practicum-dev-secret-key" not in Config.SECRET_KEY
    assert "change-me" not in Config.SECRET_KEY.lower()
    assert len(Config.SECRET_KEY) >= 16
