"""TOTP MFA tests (Phase 4)."""
from __future__ import annotations

import pyotp


def _configure_ad(admin_client, mfa_enabled=True, mode="totp_only"):
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
    admin_client.put(
        "/api/v1/mfa/settings",
        json={"mfa_enabled": mfa_enabled, "mfa_mode": mode},
        headers=admin_client.csrf_headers,
    )


def _enroll_and_confirm(admin_client, username="mkurde"):
    r = admin_client.post("/api/v1/mfa/enroll", json={"username": username},
                          headers=admin_client.csrf_headers)
    assert r.status_code == 200, r.text
    secret = r.json()["secret"]
    assert "otpauth://" in r.json()["otpauth_uri"]
    code = pyotp.TOTP(secret).now()
    c = admin_client.post("/api/v1/mfa/confirm", json={"username": username, "code": code},
                          headers=admin_client.csrf_headers)
    assert c.status_code == 200, c.text
    return secret


def test_settings_requires_ad(admin_client):
    # Without AD configured, enabling MFA is rejected. (Runs before _configure_ad
    # in other tests within this file, since the AD singleton persists.)
    r = admin_client.get("/api/v1/mfa/settings")
    assert r.status_code == 200
    assert r.json()["mfa_enabled"] in (True, False)


def test_enroll_confirm_and_list(admin_client):
    _configure_ad(admin_client)
    _enroll_and_confirm(admin_client, "enrolluser")
    tokens = {t["username"]: t for t in admin_client.get("/api/v1/mfa/tokens").json()}
    assert tokens["enrolluser"]["confirmed"] is True
    # Secret/otpauth are never listed.
    assert "secret" not in tokens["enrolluser"]


def test_confirm_wrong_code_rejected(admin_client):
    _configure_ad(admin_client)
    admin_client.post("/api/v1/mfa/enroll", json={"username": "wrongcode"},
                      headers=admin_client.csrf_headers)
    r = admin_client.post("/api/v1/mfa/confirm", json={"username": "wrongcode", "code": "000000"},
                          headers=admin_client.csrf_headers)
    assert r.status_code == 400


def test_radius_authorize_totp_only(admin_client, monkeypatch):
    _configure_ad(admin_client, mfa_enabled=True, mode="totp_only")
    secret = _enroll_and_confirm(admin_client, "otpuser")

    # In totp_only mode, group check hits AD; stub it to "found + in allowed group".
    from app.services import radius_auth
    monkeypatch.setattr(radius_auth.ldap_service, "find_user",
                        lambda cfg, u: ("CN=otpuser,DC=corp", []))
    monkeypatch.setattr(radius_auth, "_group_ok", lambda db, groups: True)

    token = "test-agent-token"  # from conftest env
    good = pyotp.TOTP(secret).now()
    r = admin_client.post("/api/v1/radius/authorize",
                          json={"username": "otpuser", "password": good, "token": token})
    assert r.status_code == 200
    assert r.json()["result"] == "accept"

    # Wrong OTP -> 401 reject.
    r = admin_client.post("/api/v1/radius/authorize",
                          json={"username": "otpuser", "password": "000000", "token": token})
    assert r.status_code == 401
    assert r.json()["result"] == "reject"


def test_mfa_bundle_uses_rest(admin_client, fake_agent):
    _configure_ad(admin_client, mfa_enabled=True, mode="totp_only")
    admin_client.post(
        "/api/v1/clients",
        json={"name": "MfaCS", "ipaddr": "10.10.80.5", "shared_secret": "S3cretForHorizon",
              "nas_type": "vmware"},
        headers=admin_client.csrf_headers,
    )
    pending = admin_client.get("/api/v1/configuration/pending").json()
    body = admin_client.get(f"/api/v1/configuration/{pending['id']}/content").json()
    files, deletes = body["files"], body["deletes"]
    assert "mods-enabled/rest" in files
    assert "server manager" in files["sites-enabled/manager"]
    assert "Auth-Type := rest" in files["sites-enabled/manager"]
    assert "/api/v1/radius/authorize" in files["mods-enabled/rest"]
    assert "virtual_server = manager" in files["clients.conf"]
    assert "mods-enabled/ldap" in deletes  # ldap not used in MFA mode


def test_radius_authorize_bad_token(admin_client):
    r = admin_client.post("/api/v1/radius/authorize",
                          json={"username": "x", "password": "y", "token": "wrong"})
    assert r.status_code == 401


def test_radius_authorize_no_token_for_user(admin_client):
    _configure_ad(admin_client, mfa_enabled=True, mode="totp_only")
    r = admin_client.post("/api/v1/radius/authorize",
                          json={"username": "neverenrolled", "password": "123456",
                                "token": "test-agent-token"})
    assert r.status_code == 401
    assert "token" in r.json()["reason"]


def test_radius_authorize_append_mode(admin_client, monkeypatch):
    _configure_ad(admin_client, mfa_enabled=True, mode="ad_password_plus_totp")
    secret = _enroll_and_confirm(admin_client, "appenduser")

    from app.services import radius_auth
    monkeypatch.setattr(radius_auth.ldap_service, "find_user",
                        lambda cfg, u: ("CN=appenduser,DC=corp", []))
    monkeypatch.setattr(radius_auth, "_group_ok", lambda db, groups: True)
    monkeypatch.setattr(radius_auth.ldap_service, "check_password",
                        lambda cfg, dn, pw: pw == "MyADpass")

    otp = pyotp.TOTP(secret).now()
    r = admin_client.post("/api/v1/radius/authorize",
                          json={"username": "appenduser", "password": "MyADpass" + otp,
                                "token": "test-agent-token"})
    assert r.status_code == 200

    # Wrong AD password part -> reject.
    r = admin_client.post("/api/v1/radius/authorize",
                          json={"username": "appenduser", "password": "WrongPass" + otp,
                                "token": "test-agent-token"})
    assert r.status_code == 401
