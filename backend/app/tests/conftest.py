"""Pytest fixtures: isolated DB, test client, authenticated helpers."""
from __future__ import annotations

import os
import tempfile

import pytest

# Configure the environment BEFORE importing the app (settings are cached and the
# DB engine is built at import time).
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db.close()

os.environ.setdefault("APP_ENV", "dev")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db.name}"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production-use-only"
os.environ["BOOTSTRAP_ADMIN_USERNAME"] = "admin"
os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = "initial-admin-pass-123"
os.environ["RADIUS_AGENT_TOKEN"] = "test-agent-token"

from cryptography.fernet import Fernet  # noqa: E402

os.environ["FERNET_KEY"] = Fernet.generate_key().decode()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import radius_agent  # noqa: E402
from app.services.seed import bootstrap_admin, init_db  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _prepare_db():
    init_db()
    bootstrap_admin()
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin_client(client):
    """A TestClient logged in as the bootstrap administrator.

    Returns the client with an attached ``csrf`` attribute and a helper to build
    headers for state-changing requests.
    """
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "initial-admin-pass-123"},
    )
    assert resp.status_code == 200, resp.text
    client.csrf_headers = {"X-CSRF-Token": client.cookies.get("radiusmgr_csrf")}
    return client


@pytest.fixture
def fake_agent(monkeypatch):
    """Replace control-agent calls with in-memory fakes (no FreeRADIUS needed)."""
    state = {"applied": None}

    def _validate(files: dict, deletes=None):
        blob = "".join(files.values())
        valid = "INVALID_MARKER" not in blob
        return {"valid": valid, "message": "ok" if valid else "syntax error",
                "details": None}

    def _apply(files: dict, deletes=None):
        state["applied"] = files
        state["deletes"] = deletes or []
        return {"success": True, "message": "reloaded", "details": None}

    def _status():
        return {"running": True}

    def _logs(limit: int = 200):
        return {"lines": ["Access-Accept"], "count": 1}

    def _test_auth(username: str, password: str):
        # Simulate accept for a magic password, reject otherwise.
        accept = password == "goodpass"
        return {"result": "Access-Accept" if accept else "Access-Reject",
                "duration_ms": 12, "details": "radclient output"}

    monkeypatch.setattr(radius_agent, "validate_config", _validate)
    monkeypatch.setattr(radius_agent, "apply_config", _apply)
    monkeypatch.setattr(radius_agent, "status", _status)
    monkeypatch.setattr(radius_agent, "logs", _logs)
    monkeypatch.setattr(radius_agent, "test_auth", _test_auth)
    return state
