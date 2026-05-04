"""Pytest fixtures shared across aggregate_analyzer tests."""

import sys
import os
import pytest

# Make the shared layer importable when pytest is run from this directory.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "shared")))


@pytest.fixture(autouse=True)
def _bypass_auth(monkeypatch):
    """
    Bypass access-key validation for unit tests.

    Production auth is fail-closed (no env var = 401). Unit tests focus on the
    handler's business logic; auth itself is covered by backend/shared tests.
    """
    import handler
    monkeypatch.setattr(handler, "validate_access_key", lambda event: True)
