"""RADIUS client CRUD + validation tests (spec sections 4, 5, 26)."""
from __future__ import annotations


def _create(admin_client, **overrides):
    payload = {
        "name": "Horizon-CS01",
        "ipaddr": "10.10.20.11",
        "shared_secret": "S3cretForHorizon",
        "nas_type": "omnissa",
    }
    payload.update(overrides)
    return admin_client.post("/api/v1/clients", json=payload, headers=admin_client.csrf_headers)


def test_nas_type_vmware_alias_normalised(admin_client):
    # The legacy "vmware" value is accepted and stored as the new "omnissa".
    r = _create(admin_client, name="LegacyNas", nas_type="vmware")
    assert r.status_code == 201, r.text
    assert r.json()["nas_type"] == "omnissa"


def test_create_and_list_client(admin_client):
    resp = _create(admin_client)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Horizon-CS01"
    # Secret must never be returned in plaintext.
    assert "shared_secret" not in body
    assert body["has_secret"] is True

    listed = admin_client.get("/api/v1/clients").json()
    assert any(c["name"] == "Horizon-CS01" for c in listed)


def test_duplicate_name_rejected(admin_client):
    _create(admin_client, name="dupe")
    resp = _create(admin_client, name="dupe")
    assert resp.status_code == 409


def test_invalid_ip_rejected(admin_client):
    resp = _create(admin_client, name="badip", ipaddr="not-an-ip")
    assert resp.status_code == 422


def test_injection_in_secret_rejected(admin_client):
    # Quote/backslash/space would break the quoted config token -> must be rejected.
    for bad in ['abc"def', "abc\\def", "abc def", 'a"}\nclient evil {']:
        resp = _create(admin_client, name="inj", shared_secret=bad)
        assert resp.status_code == 422, bad


def test_injection_in_name_rejected(admin_client):
    resp = _create(admin_client, name="evil name{")
    assert resp.status_code == 422


def test_update_and_delete(admin_client):
    created = _create(admin_client, name="ToEdit").json()
    cid = created["id"]

    upd = admin_client.put(
        f"/api/v1/clients/{cid}",
        json={"location": "Siegen", "enabled": False},
        headers=admin_client.csrf_headers,
    )
    assert upd.status_code == 200
    assert upd.json()["location"] == "Siegen"
    assert upd.json()["enabled"] is False

    d = admin_client.delete(f"/api/v1/clients/{cid}", headers=admin_client.csrf_headers)
    assert d.status_code == 204
    assert admin_client.get(f"/api/v1/clients/{cid}").status_code == 404
