"""Tests for the shared access-key validator."""

import importlib

import bcrypt
import pytest


def _bcrypt(pw: str) -> str:
    """Hash with bcrypt rounds=4 — fast for tests, never use this work factor in prod."""
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt(rounds=4)).decode("utf-8")


@pytest.fixture
def auth(monkeypatch):
    """Re-import auth.py with a clean cache and a clean env per test."""
    monkeypatch.delenv("ACCESS_PASSWORD_SECRET_NAME", raising=False)
    monkeypatch.delenv("LOCAL_PASSWORD_HASH", raising=False)
    import auth as auth_mod
    importlib.reload(auth_mod)
    auth_mod.clear_cache()
    return auth_mod


def _event(access_key=None):
    return {"headers": {"X-Access-Key": access_key} if access_key else {}}


def test_fails_closed_when_no_secret_and_no_local_hash(auth):
    """Production must reject if neither config path is set — no fail-open."""
    assert auth.validate_access_key(_event("anything")) is False


def test_rejects_when_header_missing(auth, monkeypatch):
    monkeypatch.setenv("LOCAL_PASSWORD_HASH", _bcrypt("pw"))
    assert auth.validate_access_key(_event(None)) is False


def test_local_hash_path_accepts_correct_password(auth, monkeypatch):
    monkeypatch.setenv("LOCAL_PASSWORD_HASH", _bcrypt("correct-horse"))
    assert auth.validate_access_key(_event("correct-horse")) is True


def test_local_hash_path_rejects_wrong_password(auth, monkeypatch):
    monkeypatch.setenv("LOCAL_PASSWORD_HASH", _bcrypt("correct-horse"))
    assert auth.validate_access_key(_event("wrong-password")) is False


def test_secrets_manager_path_returns_false_when_secret_empty(auth, monkeypatch):
    """If the configured secret returns an empty hash, reject."""
    monkeypatch.setenv("ACCESS_PASSWORD_SECRET_NAME", "fake-secret")
    monkeypatch.setattr(auth, "_get_password_hash", lambda: "")
    assert auth.validate_access_key(_event("anything")) is False


def test_malformed_hash_fails_closed(auth, monkeypatch):
    """A garbage stored hash must not throw or pass — return False."""
    monkeypatch.setenv("LOCAL_PASSWORD_HASH", "not-a-bcrypt-hash")
    assert auth.validate_access_key(_event("anything")) is False


def test_uses_bcrypt_checkpw(auth, monkeypatch):
    """Sanity: bcrypt.checkpw must be the comparator (not == or hashlib)."""
    monkeypatch.setenv("LOCAL_PASSWORD_HASH", _bcrypt("pw"))
    called = {"checkpw": False}
    real_checkpw = auth.bcrypt.checkpw

    def fake_checkpw(pw_bytes, hash_bytes):
        called["checkpw"] = True
        return real_checkpw(pw_bytes, hash_bytes)

    monkeypatch.setattr(auth.bcrypt, "checkpw", fake_checkpw)
    auth.validate_access_key(_event("pw"))
    assert called["checkpw"], "validate_access_key must use bcrypt.checkpw"
