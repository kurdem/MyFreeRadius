"""Config generator + lifecycle tests (spec sections 3, 15, 16)."""
from __future__ import annotations


def _create_client(admin_client, name, ip, secret="S3cretForHorizon"):
    return admin_client.post(
        "/api/v1/clients",
        json={"name": name, "ipaddr": ip, "shared_secret": secret, "nas_type": "omnissa"},
        headers=admin_client.csrf_headers,
    )


def test_generate_contains_client_and_secret(admin_client, fake_agent):
    _create_client(admin_client, "GenCS01", "10.10.30.5", secret="TopSecret99")
    pending = admin_client.get("/api/v1/configuration/pending").json()
    assert pending is not None
    content = admin_client.get(
        f"/api/v1/configuration/{pending['id']}/content"
    ).json()["files"]["clients.conf"]
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


def test_omnissa_client_gets_message_authenticator(admin_client, fake_agent):
    # NAS type omnissa defaults require_message_authenticator on (BlastRADIUS).
    r = _create_client(admin_client, "BlastCS", "10.10.60.5")
    assert r.json()["require_message_authenticator"] is True
    pending = admin_client.get("/api/v1/configuration/pending").json()
    content = admin_client.get(
        f"/api/v1/configuration/{pending['id']}/content"
    ).json()["files"]["clients.conf"]
    assert "require_message_authenticator = yes" in content


def test_non_omnissa_default_off_and_override(admin_client, fake_agent):
    # Non-omnissa defaults off.
    admin_client.post(
        "/api/v1/clients",
        json={"name": "OtherNas", "ipaddr": "10.10.61.5",
              "shared_secret": "S3cretForHorizon", "nas_type": "other"},
        headers=admin_client.csrf_headers,
    )
    # Explicit override on an omnissa client -> off.
    admin_client.post(
        "/api/v1/clients",
        json={"name": "OmnissaOff", "ipaddr": "10.10.61.6",
              "shared_secret": "S3cretForHorizon", "nas_type": "omnissa",
              "require_message_authenticator": False},
        headers=admin_client.csrf_headers,
    )
    clients = {c["name"]: c for c in admin_client.get("/api/v1/clients").json()}
    assert clients["OtherNas"]["require_message_authenticator"] is False
    assert clients["OmnissaOff"]["require_message_authenticator"] is False


def test_ad_enabled_bundle_includes_ldap_and_manager(admin_client, fake_agent):
    _create_client(admin_client, "AdCS", "10.10.70.5")
    # Configure + enable AD.
    admin_client.put(
        "/api/v1/active-directory",
        json={
            "domain": "corp.example.local", "primary_dc": "dc01.corp.example.local",
            "port": 636, "use_ldaps": True, "verify_tls": True,
            "base_dn": "DC=corp,DC=example,DC=local",
            "bind_user": "svc-radius@corp.example.local", "bind_password": "BindP4ss",
            "timeout_seconds": 5, "enabled": True,
        },
        headers=admin_client.csrf_headers,
    )
    admin_client.post(
        "/api/v1/active-directory/groups",
        json={"name": "Horizon-Users", "group_dn": "CN=Horizon-Users,OU=Groups,DC=corp,DC=example,DC=local"},
        headers=admin_client.csrf_headers,
    )
    pending = admin_client.get("/api/v1/configuration/pending").json()
    body = admin_client.get(f"/api/v1/configuration/{pending['id']}/content").json()
    files, deletes = body["files"], body["deletes"]

    assert "mods-enabled/ldap" in files
    assert "sites-enabled/manager" in files
    # We never delete the stock default site; clients route to "manager" instead.
    assert "sites-enabled/default" not in deletes
    assert "mods-enabled/rest" in deletes  # not used in ldap mode
    assert "virtual_server = manager" in files["clients.conf"]
    # LDAP module carries AD connection details and the (decrypted) bind password.
    assert "ldaps://dc01.corp.example.local" in files["mods-enabled/ldap"]
    assert "password = 'BindP4ss'" in files["mods-enabled/ldap"]
    # Manager site enforces the allowed group.
    assert "CN=Horizon-Users,OU=Groups,DC=corp,DC=example,DC=local" in files["sites-enabled/manager"]

    # Disabling AD reverts to a clients-only bundle; managed FR files are removed.
    cfg = {
        "domain": "corp.example.local", "primary_dc": "dc01.corp.example.local",
        "port": 636, "use_ldaps": True, "verify_tls": True,
        "base_dn": "DC=corp,DC=example,DC=local",
        "bind_user": "svc-radius@corp.example.local", "timeout_seconds": 5, "enabled": False,
    }
    admin_client.put("/api/v1/active-directory", json=cfg, headers=admin_client.csrf_headers)
    pending = admin_client.get("/api/v1/configuration/pending").json()
    body = admin_client.get(f"/api/v1/configuration/{pending['id']}/content").json()
    assert "mods-enabled/ldap" not in body["files"]
    assert "virtual_server = manager" not in body["files"]["clients.conf"]
    assert set(body["deletes"]) == {
        "mods-enabled/ldap", "mods-enabled/rest", "sites-enabled/manager",
        "certs/manager_ca.pem",
    }


def test_disabled_client_excluded(admin_client, fake_agent):
    r = _create_client(admin_client, "DisabledCS", "10.10.50.5")
    cid = r.json()["id"]
    admin_client.put(
        f"/api/v1/clients/{cid}", json={"enabled": False}, headers=admin_client.csrf_headers
    )
    pending = admin_client.get("/api/v1/configuration/pending").json()
    content = admin_client.get(
        f"/api/v1/configuration/{pending['id']}/content"
    ).json()["files"]["clients.conf"]
    assert "client DisabledCS {" not in content
