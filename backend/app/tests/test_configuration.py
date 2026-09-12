"""Configuration history: view content, restore an old version, delete (issue #28)."""
from __future__ import annotations

import uuid


def _unique() -> str:
    return "c" + uuid.uuid4().hex[:8]


def _add_client(admin_client, name: str) -> None:
    # A deterministic private IP derived from the unique name keeps addresses
    # from colliding across the session-scoped test database.
    h = int(name[1:], 16)
    ip = f"10.{(h >> 8) & 255}.{h & 255}.{(h >> 16) & 255}"
    r = admin_client.post(
        "/api/v1/clients",
        json={"name": name, "ipaddr": ip, "shared_secret": "s3cr3t-shared-secret"},
        headers=admin_client.csrf_headers,
    )
    assert r.status_code in (200, 201), r.text


def _generate_and_activate(admin_client) -> dict:
    pend = admin_client.get("/api/v1/configuration/pending")
    assert pend.status_code == 200, pend.text
    v = pend.json()
    act = admin_client.post(f"/api/v1/configuration/{v['id']}/activate",
                            headers=admin_client.csrf_headers)
    assert act.status_code == 200, act.text
    assert act.json()["success"] is True
    return v


def test_view_version_content(admin_client, fake_agent):
    name = _unique()
    _add_client(admin_client, name)
    v = _generate_and_activate(admin_client)
    c = admin_client.get(f"/api/v1/configuration/{v['id']}/content")
    assert c.status_code == 200, c.text
    body = c.json()
    assert body["version"] == v["version"]
    # The generated clients.conf must mention the client we added.
    blob = "".join(body["files"].values())
    assert name in blob


def test_content_requires_auth(client):
    assert client.get("/api/v1/configuration/1/content").status_code == 401


def test_restore_old_version(admin_client, fake_agent):
    older = _unique()
    _add_client(admin_client, older)
    first = _generate_and_activate(admin_client)

    # A brand-new, unique client that did NOT exist when `first` was generated.
    newer = _unique()
    _add_client(admin_client, newer)
    _generate_and_activate(admin_client)

    # Restore the first version -> a NEW version becomes active with old content.
    r = admin_client.post(f"/api/v1/configuration/{first['id']}/restore",
                          headers=admin_client.csrf_headers)
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True

    hist = admin_client.get("/api/v1/configuration/history").json()
    active = next(h for h in hist if h["state"] == "active")
    # New version number, but content restored from the first one.
    assert active["version"] > first["version"]
    content = admin_client.get(f"/api/v1/configuration/{active['id']}/content").json()
    blob = "".join(content["files"].values())
    assert older in blob and newer not in blob


def test_cannot_restore_active(admin_client, fake_agent):
    _add_client(admin_client, _unique())
    v = _generate_and_activate(admin_client)
    r = admin_client.post(f"/api/v1/configuration/{v['id']}/restore",
                          headers=admin_client.csrf_headers)
    assert r.status_code == 400
    assert "already active" in r.json()["detail"].lower()


def test_delete_non_active_version(admin_client, fake_agent):
    _add_client(admin_client, _unique())
    first = _generate_and_activate(admin_client)
    _add_client(admin_client, _unique())
    _generate_and_activate(admin_client)

    # The first version is now PREVIOUS and may be deleted.
    d = admin_client.delete(f"/api/v1/configuration/{first['id']}",
                            headers=admin_client.csrf_headers)
    assert d.status_code == 204, d.text
    versions = {h["id"] for h in admin_client.get("/api/v1/configuration/history").json()}
    assert first["id"] not in versions


def test_cannot_delete_active_version(admin_client, fake_agent):
    _add_client(admin_client, _unique())
    v = _generate_and_activate(admin_client)
    d = admin_client.delete(f"/api/v1/configuration/{v['id']}",
                            headers=admin_client.csrf_headers)
    assert d.status_code == 400
    assert "active" in d.json()["detail"].lower()


def test_delete_requires_admin(client):
    assert client.delete("/api/v1/configuration/1").status_code == 401
