"""Active Directory config, groups and connection-test tests (Phase 3)."""
from __future__ import annotations

import sys
import types


def _cfg_payload(**overrides):
    payload = {
        "domain": "corp.example.local",
        "primary_dc": "dc01.corp.example.local",
        "secondary_dc": "dc02.corp.example.local",
        "port": 636,
        "use_ldaps": True,
        "verify_tls": True,
        "base_dn": "DC=corp,DC=example,DC=local",
        "bind_user": "svc-radius@corp.example.local",
        "bind_password": "Sup3rBindP@ss",
        "timeout_seconds": 5,
        "enabled": True,
    }
    payload.update(overrides)
    return payload


def test_ad_not_configured_returns_null(admin_client):
    assert admin_client.get("/api/v1/active-directory").json() is None


def test_create_requires_password(admin_client):
    p = _cfg_payload()
    p.pop("bind_password")
    r = admin_client.put("/api/v1/active-directory", json=p, headers=admin_client.csrf_headers)
    assert r.status_code == 400


def test_create_and_get_hides_password(admin_client):
    r = admin_client.put(
        "/api/v1/active-directory", json=_cfg_payload(), headers=admin_client.csrf_headers
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "bind_password" not in body
    assert body["has_bind_password"] is True
    assert body["domain"] == "corp.example.local"
    # Update without password keeps it.
    upd = _cfg_payload(enabled=False)
    upd.pop("bind_password")
    r2 = admin_client.put("/api/v1/active-directory", json=upd, headers=admin_client.csrf_headers)
    assert r2.status_code == 200
    assert r2.json()["enabled"] is False
    assert r2.json()["has_bind_password"] is True


def test_invalid_host_and_dn_rejected(admin_client):
    assert admin_client.put(
        "/api/v1/active-directory",
        json=_cfg_payload(primary_dc="bad host!"),
        headers=admin_client.csrf_headers,
    ).status_code == 422
    assert admin_client.put(
        "/api/v1/active-directory",
        json=_cfg_payload(base_dn='DC="inject"'),
        headers=admin_client.csrf_headers,
    ).status_code == 422


def test_groups_crud(admin_client):
    r = admin_client.post(
        "/api/v1/active-directory/groups",
        json={"name": "Horizon-Users", "group_dn": "CN=Horizon-Users,OU=Groups,DC=corp,DC=example,DC=local"},
        headers=admin_client.csrf_headers,
    )
    assert r.status_code == 201
    gid = r.json()["id"]
    # duplicate DN -> conflict
    dup = admin_client.post(
        "/api/v1/active-directory/groups",
        json={"name": "dupe", "group_dn": "CN=Horizon-Users,OU=Groups,DC=corp,DC=example,DC=local"},
        headers=admin_client.csrf_headers,
    )
    assert dup.status_code == 409
    assert any(g["name"] == "Horizon-Users" for g in admin_client.get("/api/v1/active-directory/groups").json())
    assert admin_client.delete(
        f"/api/v1/active-directory/groups/{gid}", headers=admin_client.csrf_headers
    ).status_code == 204


def test_connection_test_endpoint(admin_client, monkeypatch):
    admin_client.put("/api/v1/active-directory", json=_cfg_payload(), headers=admin_client.csrf_headers)
    from app.api import active_directory as ad_api

    monkeypatch.setattr(
        ad_api.ldap_service, "test_connection",
        lambda cfg: {"success": True, "message": "ok", "details": "dc01: bind OK"},
    )
    r = admin_client.post("/api/v1/active-directory/test", headers=admin_client.csrf_headers)
    assert r.status_code == 200
    assert r.json()["success"] is True


def test_ldap_service_success_with_fake_ldap3(admin_client, monkeypatch):
    """Exercise ldap_service against an injected fake ldap3 (no real DC)."""
    admin_client.put("/api/v1/active-directory", json=_cfg_payload(use_ldaps=False, port=389),
                     headers=admin_client.csrf_headers)

    captured = {}

    class FakeConnection:
        def __init__(self, server, user=None, password=None, **kw):
            captured["user"] = user
            captured["password"] = password
            self.server = server

        def search(self, **kw):
            return True

        def unbind(self):
            pass

    fake = types.ModuleType("ldap3")
    fake.BASE = "BASE"
    fake.Server = lambda *a, **k: types.SimpleNamespace(**k)
    fake.Connection = FakeConnection
    fake.Tls = lambda **k: object()
    core = types.ModuleType("ldap3.core")
    exc_mod = types.ModuleType("ldap3.core.exceptions")

    class LDAPException(Exception):
        pass

    exc_mod.LDAPException = LDAPException
    core.exceptions = exc_mod
    monkeypatch.setitem(sys.modules, "ldap3", fake)
    monkeypatch.setitem(sys.modules, "ldap3.core", core)
    monkeypatch.setitem(sys.modules, "ldap3.core.exceptions", exc_mod)

    from app.services import ldap_service
    from app.models import ADConfig
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        cfg = db.get(ADConfig, 1)
        result = ldap_service.test_connection(cfg)
    finally:
        db.close()

    assert result["success"] is True
    # The real bind password was decrypted and passed to the client, not logged.
    assert captured["password"] == "Sup3rBindP@ss"
