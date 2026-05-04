"""Tests for the shared access-key validator."""

import hashlib
import importlib

import pytest


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
    monkeypatch.setenv("LOCAL_PASSWORD_HASH", hashlib.sha256(b"pw").hexdigest())
    assert auth.validate_access_key(_event(None)) is False


def test_local_hash_path_accepts_correct_password(auth, monkeypatch):
    monkeypatch.setenv("LOCAL_PASSWORD_HASH", hashlib.sha256(b"correct-horse").hexdigest())
    assert auth.validate_access_key(_event("correct-horse")) is True


def test_local_hash_path_rejects_wrong_password(auth, monkeypatch):
    monkeypatch.setenv("LOCAL_PASSWORD_HASH", hashlib.sha256(b"correct-horse").hexdigest())
    assert auth.validate_access_key(_event("wrong-password")) is False


def test_secrets_manager_path_returns_false_when_secret_empty(auth, monkeypatch):
    """If the configured secret returns an empty hash, reject."""
    monkeypatch.setenv("ACCESS_PASSWORD_SECRET_NAME", "fake-secret")
    monkeypatch.setattr(auth, "_get_password_hash", lambda: "")
    assert auth.validate_access_key(_event("anything")) is False


def test_uses_constant_time_compare(auth, monkeypatch):
    """Sanity: hmac.compare_digest must be the comparator (not ==)."""
    monkeypatch.setenv("LOCAL_PASSWORD_HASH", hashlib.sha256(b"pw").hexdigest())
    called = {"compare_digest": False}

    def fake_compare(a, b):
        called["compare_digest"] = True
        return a == b

    monkeypatch.setattr(auth.hmac, "compare_digest", fake_compare)
    auth.validate_access_key(_event("pw"))
    assert called["compare_digest"], "validate_access_key must use hmac.compare_digest"
