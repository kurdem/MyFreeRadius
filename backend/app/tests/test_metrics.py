"""Metrics + deep-health tests (monitoring MVP)."""
from __future__ import annotations


def test_metrics_endpoint_public(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]
    body = r.text
    assert "radiusmgr_radius_clients" in body
    assert "radiusmgr_freeradius_up" in body
    assert "radiusmgr_info" in body


def test_test_auth_increments_counter(admin_client, fake_agent, client):
    before = client.get("/metrics").text
    admin_client.post("/api/v1/radius/test", json={"username": "m", "password": "wrong"},
                      headers=admin_client.csrf_headers)
    after = client.get("/metrics").text
    # A reject test-auth counter sample must be present after the call.
    assert 'radiusmgr_test_total{result="reject"}' in after
    assert before != after


def test_health_detailed(admin_client):
    r = admin_client.get("/api/v1/health/detailed")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("OK", "WARNING", "CRITICAL")
    names = {c["name"] for c in body["components"]}
    assert {"application", "database", "freeradius", "certificates"} <= names
    db = next(c for c in body["components"] if c["name"] == "database")
    assert db["status"] == "OK"


def test_health_detailed_requires_auth(client):
    assert client.get("/api/v1/health/detailed").status_code == 401
