"""Authentication, session, CSRF and lockout tests (spec sections 21, 22)."""
from __future__ import annotations


def test_login_success_sets_cookies(client):
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "initial-admin-pass-123"},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "administrator"
    assert client.cookies.get("radiusmgr_session")
    assert client.cookies.get("radiusmgr_csrf")


def test_login_wrong_password_is_401_generic(client):
    resp = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "wrong"}
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid username or password"


def test_unknown_user_same_error_as_wrong_password(client):
    resp = client.post(
        "/api/v1/auth/login", json={"username": "nope", "password": "whatever"}
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid username or password"


def test_me_requires_auth(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_csrf_required_for_mutations(admin_client):
    # Create client WITHOUT the CSRF header -> rejected.
    resp = admin_client.post(
        "/api/v1/clients",
        json={"name": "x", "ipaddr": "10.0.0.1", "shared_secret": "secret123"},
    )
    assert resp.status_code == 403
    assert "CSRF" in resp.json()["detail"]
