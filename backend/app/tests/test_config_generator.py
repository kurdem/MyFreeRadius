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


def test_vmware_client_gets_message_authenticator(admin_client, fake_agent):
    # NAS type vmware defaults require_message_authenticator on (BlastRADIUS).
    r = _create_client(admin_client, "BlastCS", "10.10.60.5")
    assert r.json()["require_message_authenticator"] is True
    pending = admin_client.get("/api/v1/configuration/pending").json()
    content = admin_client.get(
        f"/api/v1/configuration/{pending['id']}/content"
    ).json()["content"]
    assert "require_message_authenticator = yes" in content


def test_non_vmware_default_off_and_override(admin_client, fake_agent):
    # Non-vmware defaults off.
    admin_client.post(
        "/api/v1/clients",
        json={"name": "OtherNas", "ipaddr": "10.10.61.5",
              "shared_secret": "S3cretForHorizon", "nas_type": "other"},
        headers=admin_client.csrf_headers,
    )
    # Explicit override on a vmware client -> off.
    admin_client.post(
        "/api/v1/clients",
        json={"name": "VmwareOff", "ipaddr": "10.10.61.6",
              "shared_secret": "S3cretForHorizon", "nas_type": "vmware",
              "require_message_authenticator": False},
        headers=admin_client.csrf_headers,
    )
    clients = {c["name"]: c for c in admin_client.get("/api/v1/clients").json()}
    assert clients["OtherNas"]["require_message_authenticator"] is False
    assert clients["VmwareOff"]["require_message_authenticator"] is False


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
