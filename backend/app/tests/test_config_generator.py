"""Config generator + lifecycle tests (spec sections 3, 15, 16)."""
from __future__ import annotations


def _create_client(admin_client, name, ip, secret="S3cretForHorizon"):
    return admin_client.post(
        "/api/v1/clients",
        json={"name": name, "ipaddr": ip, "shared_secret": secret, "nas_type": "vmware"},
        headers=admin_client.csrf_headers,
    )


def test_generate_contains_client_and_secret(admin_client, fake_agent):
    _create_client(admin_client, "GenCS01", "10.10.30.5", secret="TopSecret99")
    pending = admin_client.get("/api/v1/configuration/pending").json()
    assert pending is not None
    content = admin_client.get(
        f"/api/v1/configuration/{pending['id']}/content"
    ).json()["content"]
    assert "client GenCS01 {" in content
    assert "10.10.30.5" in content
    # Secret is decrypted into the generated config (FreeRADIUS needs it).
    assert 'secret    = "TopSecret99"' in content


def test_validate_and_activate_flow(admin_client, fake_agent):
    _create_client(admin_client, "FlowCS01", "10.10.40.5")
    pending = admin_client.get("/api/v1/configuration/pending").json()
    vid = pending["id"]

    val = admin_client.post(
        f"/api/v1/configuration/{vid}/validate", headers=admin_client.csrf_headers
    ).json()
    assert val["valid"] is True

    act = admin_client.post(
        f"/api/v1/configuration/{vid}/activate", headers=admin_client.csrf_headers
    ).json()
    assert act["success"] is True
    assert fake_agent["applied"] is not None

    history = admin_client.get("/api/v1/configuration/history").json()
    assert any(v["state"] == "active" for v in history)


def test_disabled_client_excluded(admin_client, fake_agent):
    r = _create_client(admin_client, "DisabledCS", "10.10.50.5")
    cid = r.json()["id"]
    admin_client.put(
        f"/api/v1/clients/{cid}", json={"enabled": False}, headers=admin_client.csrf_headers
    )
    pending = admin_client.get("/api/v1/configuration/pending").json()
    content = admin_client.get(
        f"/api/v1/configuration/{pending['id']}/content"
    ).json()["content"]
    assert "client DisabledCS {" not in content
