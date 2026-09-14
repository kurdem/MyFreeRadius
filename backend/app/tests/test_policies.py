"""Authentication policy tests (Phase 7): engine, CRUD, authorize, generation."""
from __future__ import annotations

import pyotp


# --------------------------------------------------------------------------- #
# Engine (unit)
# --------------------------------------------------------------------------- #
def test_engine_first_match_and_defaults():
    from app.database import SessionLocal
    from app.models import AuthPolicy, PolicyAction
    from app.services import policy_service

    db = SessionLocal()
    try:
        # Clean slate for a deterministic engine test.
        for p in db.query(AuthPolicy).all():
            db.delete(p)
        db.commit()

        # No policies -> not restricting.
        d = policy_service.evaluate(db, client_group_id=None, user_group_dns=[])
        assert d.had_policies is False and d.allow is True

        # deny (priority 10) beats a later allow (priority 20) for the same group.
        db.add(AuthPolicy(name="deny-vpn", priority=10, action=PolicyAction.DENY,
                          ad_group_dn="CN=VPN,DC=corp"))
        db.add(AuthPolicy(name="allow-all", priority=20, action=PolicyAction.ALLOW,
                          reply_attributes='[{"name":"Filter-Id","value":"std"}]'))
        db.commit()

        denied = policy_service.evaluate(db, client_group_id=None,
                                         user_group_dns=["CN=VPN,DC=corp"])
        assert denied.had_policies is True and denied.allow is False

        allowed = policy_service.evaluate(db, client_group_id=None,
                                          user_group_dns=["CN=Other,DC=corp"])
        assert allowed.allow is True
        assert allowed.reply_attributes == [{"name": "Filter-Id", "value": "std"}]

        # Remove the catch-all allow -> a non-matching request is default-denied.
        db.query(AuthPolicy).filter(AuthPolicy.name == "allow-all").delete()
        db.commit()
        d2 = policy_service.evaluate(db, client_group_id=None, user_group_dns=["CN=Other,DC=corp"])
        assert d2.had_policies is True and d2.allow is False

        # Cleanup so other tests start clean.
        for p in db.query(AuthPolicy).all():
            db.delete(p)
        db.commit()
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# CRUD API
# --------------------------------------------------------------------------- #
def test_policy_crud(admin_client):
    r = admin_client.post(
        "/api/v1/policies",
        json={"name": "Allow admins", "priority": 5, "action": "allow",
              "ad_group_dn": "CN=Admins,DC=corp", "ad_group_name": "Admins",
              "reply_attributes": [{"name": "Filter-Id", "value": "admin"}]},
        headers=admin_client.csrf_headers,
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert r.json()["reply_attributes"] == [{"name": "Filter-Id", "value": "admin"}]

    lst = admin_client.get("/api/v1/policies").json()
    assert any(p["id"] == pid for p in lst)

    u = admin_client.put(f"/api/v1/policies/{pid}", json={"enabled": False, "priority": 7},
                         headers=admin_client.csrf_headers)
    assert u.status_code == 200 and u.json()["enabled"] is False and u.json()["priority"] == 7

    d = admin_client.delete(f"/api/v1/policies/{pid}", headers=admin_client.csrf_headers)
    assert d.status_code == 204
    assert all(p["id"] != pid for p in admin_client.get("/api/v1/policies").json())


def test_policy_bad_client_group(admin_client):
    r = admin_client.post("/api/v1/policies",
                          json={"name": "x", "client_group_id": 999999},
                          headers=admin_client.csrf_headers)
    assert r.status_code == 400


def test_policy_write_requires_admin(client):
    assert client.post("/api/v1/policies", json={"name": "x"}).status_code == 401


# --------------------------------------------------------------------------- #
# authorize integration
# --------------------------------------------------------------------------- #
def _configure_ad(admin_client, mfa_enabled=True):
    admin_client.put(
        "/api/v1/active-directory",
        json={"domain": "corp.example.local", "primary_dc": "dc01.corp.example.local",
              "port": 636, "use_ldaps": True, "verify_tls": True,
              "base_dn": "DC=corp,DC=example,DC=local",
              "bind_user": "svc@corp.example.local", "bind_password": "BindP4ss",
              "timeout_seconds": 5, "enabled": True},
        headers=admin_client.csrf_headers,
    )
    admin_client.put("/api/v1/mfa/settings",
                     json={"mfa_enabled": mfa_enabled, "mfa_mode": "totp_only"},
                     headers=admin_client.csrf_headers)


def _enroll(admin_client, username):
    r = admin_client.post("/api/v1/mfa/enroll", json={"username": username},
                          headers=admin_client.csrf_headers)
    secret = r.json()["secret"]
    code = pyotp.TOTP(secret).now()
    admin_client.post("/api/v1/mfa/confirm", json={"username": username, "code": code},
                      headers=admin_client.csrf_headers)
    return secret


def test_policy_denies_valid_mfa_user(admin_client, monkeypatch):
    _configure_ad(admin_client, mfa_enabled=True)
    secret = _enroll(admin_client, "poluser")

    from app.services import radius_auth
    # User is a member of the VPN group; MFA + coarse group gate pass.
    monkeypatch.setattr(radius_auth.ldap_service, "find_user",
                        lambda cfg, u, **kw: ("CN=poluser,DC=corp", ["CN=VPN,DC=corp"]))
    monkeypatch.setattr(radius_auth, "_group_ok", lambda db, groups: True)

    token = "test-agent-token"
    # A deny policy on the VPN group must block an otherwise-valid login.
    pol = admin_client.post("/api/v1/policies",
                            json={"name": "block vpn", "priority": 1, "action": "deny",
                                  "ad_group_dn": "CN=VPN,DC=corp"},
                            headers=admin_client.csrf_headers).json()

    r = admin_client.post("/api/v1/radius/authorize",
                          json={"username": "poluser", "password": pyotp.TOTP(secret).now(),
                                "token": token})
    assert r.status_code == 401
    assert r.json()["result"] == "reject"

    # Remove the deny policy -> the same login succeeds again.
    admin_client.delete(f"/api/v1/policies/{pol['id']}", headers=admin_client.csrf_headers)
    r = admin_client.post("/api/v1/radius/authorize",
                          json={"username": "poluser", "password": pyotp.TOTP(secret).now(),
                                "token": token})
    assert r.status_code == 200, r.text
    assert r.json()["result"] == "accept"


def test_policy_returns_reply_attributes(admin_client, monkeypatch):
    _configure_ad(admin_client, mfa_enabled=True)
    secret = _enroll(admin_client, "replyuser")

    from app.services import radius_auth
    monkeypatch.setattr(radius_auth.ldap_service, "find_user",
                        lambda cfg, u, **kw: ("CN=replyuser,DC=corp", ["CN=Staff,DC=corp"]))
    monkeypatch.setattr(radius_auth, "_group_ok", lambda db, groups: True)

    pol = admin_client.post("/api/v1/policies",
                            json={"name": "staff filter", "priority": 1, "action": "allow",
                                  "ad_group_dn": "CN=Staff,DC=corp",
                                  "reply_attributes": [{"name": "Filter-Id", "value": "staff-acl"}]},
                            headers=admin_client.csrf_headers).json()
    r = admin_client.post("/api/v1/radius/authorize",
                          json={"username": "replyuser", "password": pyotp.TOTP(secret).now(),
                                "token": "test-agent-token"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["result"] == "accept"
    assert body["reply:Filter-Id"]["value"] == "staff-acl"
    admin_client.delete(f"/api/v1/policies/{pol['id']}", headers=admin_client.csrf_headers)


# --------------------------------------------------------------------------- #
# config generation
# --------------------------------------------------------------------------- #
def test_active_policy_routes_to_backend_without_mfa(admin_client, fake_agent):
    # AD on, MFA OFF, but an enabled policy exists -> manager site must delegate
    # to the backend (rest), not the plain LDAP site.
    _configure_ad(admin_client, mfa_enabled=False)
    pol = admin_client.post("/api/v1/policies",
                            json={"name": "route", "priority": 1, "action": "allow"},
                            headers=admin_client.csrf_headers).json()
    admin_client.post("/api/v1/clients",
                      json={"name": "PolCS", "ipaddr": "10.20.0.5",
                            "shared_secret": "S3cretForHorizon", "nas_type": "omnissa"},
                      headers=admin_client.csrf_headers)
    pending = admin_client.get("/api/v1/configuration/pending").json()
    files = admin_client.get(f"/api/v1/configuration/{pending['id']}/content").json()["files"]
    assert "mods-enabled/rest" in files
    assert "Auth-Type := rest" in files["sites-enabled/manager"]
    assert "client_shortname" in files["mods-enabled/rest"]
    admin_client.delete(f"/api/v1/policies/{pol['id']}", headers=admin_client.csrf_headers)
