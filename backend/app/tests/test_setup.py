"""Setup wizard status tests (spec section 38)."""
from __future__ import annotations


def test_status_and_complete(admin_client):
    s = admin_client.get("/api/v1/setup/status").json()
    assert "setup_completed" in s
    assert "administrator" in s["checklist"]
    assert s["checklist"]["administrator"] is True  # bootstrap admin exists

    done = admin_client.post("/api/v1/setup/complete", headers=admin_client.csrf_headers)
    assert done.status_code == 200
    assert done.json()["setup_completed"] is True
    assert admin_client.get("/api/v1/setup/status").json()["setup_completed"] is True

    # Re-open.
    admin_client.post("/api/v1/setup/reset", headers=admin_client.csrf_headers)
    assert admin_client.get("/api/v1/setup/status").json()["setup_completed"] is False


def test_status_requires_auth(client):
    assert client.get("/api/v1/setup/status").status_code == 401
