"""Backup / restore tests (spec section 17)."""
from __future__ import annotations

import json


def _make_client(admin_client, name, ip):
    return admin_client.post(
        "/api/v1/clients",
        json={"name": name, "ipaddr": ip, "shared_secret": "S3cretForHorizon", "nas_type": "vmware"},
        headers=admin_client.csrf_headers,
    )


def test_export_restore_roundtrip(admin_client):
    _make_client(admin_client, "BackupCS", "10.20.0.5")
    before = {c["name"] for c in admin_client.get("/api/v1/clients").json()}
    assert "BackupCS" in before

    # Export.
    exp = admin_client.post("/api/v1/backup/export", json={}, headers=admin_client.csrf_headers)
    assert exp.status_code == 200
    assert "attachment" in exp.headers["content-disposition"]
    blob = exp.content
    data = json.loads(blob)
    assert data["format"].startswith("freeradius-manager-backup/")
    assert any(r["name"] == "BackupCS" for r in data["tables"]["radius_clients"])

    # Delete the client, then restore.
    cid = next(c["id"] for c in admin_client.get("/api/v1/clients").json() if c["name"] == "BackupCS")
    admin_client.delete(f"/api/v1/clients/{cid}", headers=admin_client.csrf_headers)
    assert not any(c["name"] == "BackupCS" for c in admin_client.get("/api/v1/clients").json())

    r = admin_client.post(
        "/api/v1/backup/restore",
        files={"file": ("backup.json", blob, "application/octet-stream")},
        headers=admin_client.csrf_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["restored"]["radius_clients"] >= 1
    assert any(c["name"] == "BackupCS" for c in admin_client.get("/api/v1/clients").json())
    # Secret is still usable (decryptable) after restore -> config generates.
    pending = admin_client.get("/api/v1/configuration/pending").json()
    content = admin_client.get(f"/api/v1/configuration/{pending['id']}/content").json()
    assert "client BackupCS {" in content["files"]["clients.conf"]


def test_encrypted_backup_roundtrip(admin_client):
    _make_client(admin_client, "EncCS", "10.20.0.6")
    exp = admin_client.post("/api/v1/backup/export", json={"passphrase": "s3cret pass"},
                            headers=admin_client.csrf_headers)
    assert exp.status_code == 200
    blob = exp.content
    env = json.loads(blob)
    assert env["format"] == "freeradius-manager-backup-encrypted/1"

    # Wrong passphrase -> 400.
    bad = admin_client.post(
        "/api/v1/backup/restore",
        files={"file": ("b.enc.json", blob, "application/octet-stream")},
        data={"passphrase": "wrong"},
        headers=admin_client.csrf_headers,
    )
    assert bad.status_code == 400

    # Correct passphrase -> restored.
    ok = admin_client.post(
        "/api/v1/backup/restore",
        files={"file": ("b.enc.json", blob, "application/octet-stream")},
        data={"passphrase": "s3cret pass"},
        headers=admin_client.csrf_headers,
    )
    assert ok.status_code == 200


def test_restore_garbage_rejected(admin_client):
    r = admin_client.post(
        "/api/v1/backup/restore",
        files={"file": ("x.json", b"not a backup", "application/octet-stream")},
        headers=admin_client.csrf_headers,
    )
    assert r.status_code == 400


def test_restore_requires_admin(admin_client):
    # The export endpoint requires a session; no cookies -> 401.
    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as anon:
        assert anon.post("/api/v1/backup/export", json={}).status_code == 401
