"""CA certificate management tests (spec section 11)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


def _make_cert(cn: str = "Corp Root CA", days_valid: int = 3650) -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=days_valid))
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def test_upload_list_get_delete(admin_client):
    pem = _make_cert("Corp Root CA 1")
    r = admin_client.post("/api/v1/certificates", json={"name": "Corp Root", "pem": pem},
                          headers=admin_client.csrf_headers)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "valid"
    assert "CN=Corp Root CA 1" in body["subject"]
    assert body["days_left"] > 3000
    cid = body["id"]

    # PEM download.
    p = admin_client.get(f"/api/v1/certificates/{cid}/pem")
    assert p.status_code == 200
    assert "BEGIN CERTIFICATE" in p.text

    assert any(c["id"] == cid for c in admin_client.get("/api/v1/certificates").json())

    d = admin_client.delete(f"/api/v1/certificates/{cid}", headers=admin_client.csrf_headers)
    assert d.status_code == 204


def test_duplicate_rejected(admin_client):
    pem = _make_cert("Dup CA")
    admin_client.post("/api/v1/certificates", json={"name": "a", "pem": pem},
                      headers=admin_client.csrf_headers)
    r = admin_client.post("/api/v1/certificates", json={"name": "b", "pem": pem},
                          headers=admin_client.csrf_headers)
    assert r.status_code == 409


def test_invalid_pem_rejected(admin_client):
    r = admin_client.post("/api/v1/certificates",
                          json={"name": "bad", "pem": "not a certificate"},
                          headers=admin_client.csrf_headers)
    assert r.status_code == 400


def test_expiring_status(admin_client):
    pem = _make_cert("Soon CA", days_valid=10)
    r = admin_client.post("/api/v1/certificates", json={"name": "soon", "pem": pem},
                          headers=admin_client.csrf_headers)
    assert r.status_code == 201
    assert r.json()["status"] == "expiring"


def test_ldap_bundle_includes_ca(admin_client, fake_agent):
    # Configure AD (LDAPS) + a CA cert, then the ldap-mode bundle should carry it.
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
    # Ensure MFA is off so the ldap-mode bundle is generated.
    admin_client.put("/api/v1/mfa/settings", json={"mfa_enabled": False, "mfa_mode": "totp_only"},
                     headers=admin_client.csrf_headers)
    admin_client.post("/api/v1/certificates",
                      json={"name": "AD Root", "pem": _make_cert("AD Root CA")},
                      headers=admin_client.csrf_headers)
    admin_client.post(
        "/api/v1/clients",
        json={"name": "CertCS", "ipaddr": "10.10.90.5", "shared_secret": "S3cretForHorizon",
              "nas_type": "vmware"},
        headers=admin_client.csrf_headers,
    )
    pending = admin_client.get("/api/v1/configuration/pending").json()
    body = admin_client.get(f"/api/v1/configuration/{pending['id']}/content").json()
    assert "certs/manager_ca.pem" in body["files"]
    assert "BEGIN CERTIFICATE" in body["files"]["certs/manager_ca.pem"]
    assert "ca_file = ${certdir}/manager_ca.pem" in body["files"]["mods-enabled/ldap"]
