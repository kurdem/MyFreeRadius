"""Test Authentication endpoint (spec section 12)."""
from __future__ import annotations


def test_test_auth_accept(admin_client, fake_agent):
    r = admin_client.post(
        "/api/v1/radius/test",
        json={"username": "mkurde", "password": "goodpass"},
        headers=admin_client.csrf_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["result"] == "Access-Accept"
    assert body["accepted"] is True


def test_test_auth_reject(admin_client, fake_agent):
    r = admin_client.post(
        "/api/v1/radius/test",
        json={"username": "mkurde", "password": "wrong"},
        headers=admin_client.csrf_headers,
    )
    assert r.status_code == 200
    assert r.json()["accepted"] is False


def test_auth_events_records_result(admin_client, fake_agent):
    admin_client.post("/api/v1/radius/test", json={"username": "eventuser", "password": "wrong"},
                      headers=admin_client.csrf_headers)
    events = admin_client.get("/api/v1/logs/auth-events").json()
    ours = [e for e in events if e["username"] == "eventuser"]
    assert ours, "expected an auth event for eventuser"
    assert ours[0]["result"] == "FAILURE"
    assert ours[0]["source"] == "test"
    assert ours[0]["reason"]  # carries the reject reason


def test_test_auth_requires_auth(client):
    # No session -> 401 (this is a UI endpoint, not the machine one).
    assert client.post("/api/v1/radius/test",
                       json={"username": "x", "password": "y"}).status_code == 401


def test_test_auth_rejects_injection(admin_client, fake_agent):
    r = admin_client.post(
        "/api/v1/radius/test",
        json={"username": 'a" evil', "password": "x"},
        headers=admin_client.csrf_headers,
    )
    assert r.status_code == 422
