"""Local user administration tests (issue #7)."""
from __future__ import annotations


def test_create_list_update_delete(admin_client):
    r = admin_client.post(
        "/api/v1/users",
        json={"username": "operator1", "password": "operator-pass-123", "role": "operator"},
        headers=admin_client.csrf_headers,
    )
    assert r.status_code == 201, r.text
    uid = r.json()["id"]
    assert r.json()["role"] == "operator"

    assert any(u["username"] == "operator1" for u in admin_client.get("/api/v1/users").json())

    # Promote + reset password.
    upd = admin_client.put(f"/api/v1/users/{uid}",
                           json={"role": "auditor", "password": "new-operator-pass-1"},
                           headers=admin_client.csrf_headers)
    assert upd.status_code == 200
    assert upd.json()["role"] == "auditor"

    d = admin_client.delete(f"/api/v1/users/{uid}", headers=admin_client.csrf_headers)
    assert d.status_code == 204


def test_duplicate_username_rejected(admin_client):
    admin_client.post("/api/v1/users",
                      json={"username": "dupe", "password": "some-password-12", "role": "operator"},
                      headers=admin_client.csrf_headers)
    r = admin_client.post("/api/v1/users",
                          json={"username": "dupe", "password": "some-password-12", "role": "operator"},
                          headers=admin_client.csrf_headers)
    assert r.status_code == 409


def test_short_password_rejected(admin_client):
    r = admin_client.post("/api/v1/users",
                          json={"username": "shortpw", "password": "short", "role": "operator"},
                          headers=admin_client.csrf_headers)
    assert r.status_code == 422


def test_cannot_remove_last_admin(admin_client):
    # The bootstrap admin is the only administrator; demoting/deactivating it must fail.
    me = admin_client.get("/api/v1/auth/me").json()
    r = admin_client.put(f"/api/v1/users/{me['id']}", json={"role": "operator"},
                         headers=admin_client.csrf_headers)
    assert r.status_code == 400
    r2 = admin_client.put(f"/api/v1/users/{me['id']}", json={"is_active": False},
                          headers=admin_client.csrf_headers)
    assert r2.status_code == 400
    # And cannot delete self.
    r3 = admin_client.delete(f"/api/v1/users/{me['id']}", headers=admin_client.csrf_headers)
    assert r3.status_code == 400


def test_requires_admin(client):
    assert client.get("/api/v1/users").status_code == 401
