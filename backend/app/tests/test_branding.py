"""Branding tests (issue #20)."""
from __future__ import annotations

# 1x1 transparent PNG.
_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
    b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_default_branding_public(client):
    r = client.get("/api/v1/branding")
    assert r.status_code == 200
    assert r.json()["app_title"] == "FreeRADIUS Manager"
    assert r.json()["otp_issuer"] == "FreeRADIUS Manager"
    assert r.json()["has_logo"] is False
    # No logo yet.
    assert client.get("/api/v1/branding/logo").status_code == 404


def test_set_otp_issuer_used_by_mfa(admin_client):
    r = admin_client.put(
        "/api/v1/branding",
        data={"otp_issuer": "ACME Corp"},
        headers=admin_client.csrf_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["otp_issuer"] == "ACME Corp"

    # A new enrollment must embed the configured issuer in the otpauth URI.
    enr = admin_client.post("/api/v1/mfa/enroll", json={"username": "alice"},
                            headers=admin_client.csrf_headers)
    assert enr.status_code == 200, enr.text
    assert "issuer=ACME%20Corp" in enr.json()["otpauth_uri"]


def test_set_title_and_logo(admin_client, client):
    r = admin_client.put(
        "/api/v1/branding",
        data={"app_title": "SVA RADIUS"},
        files={"logo": ("logo.png", _PNG, "image/png")},
        headers=admin_client.csrf_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["app_title"] == "SVA RADIUS"
    assert r.json()["has_logo"] is True

    # Public reads reflect it.
    pub = client.get("/api/v1/branding").json()
    assert pub["app_title"] == "SVA RADIUS"
    assert pub["has_logo"] is True
    logo = client.get("/api/v1/branding/logo")
    assert logo.status_code == 200
    assert logo.headers["content-type"] == "image/png"
    assert logo.content == _PNG

    # Remove the logo again.
    rm = admin_client.put("/api/v1/branding", data={"remove_logo": "true"},
                          headers=admin_client.csrf_headers)
    assert rm.status_code == 200
    assert rm.json()["has_logo"] is False


def test_reject_non_image(admin_client):
    r = admin_client.put(
        "/api/v1/branding",
        files={"logo": ("x.txt", b"hello", "text/plain")},
        data={"app_title": ""},
        headers=admin_client.csrf_headers,
    )
    assert r.status_code == 400


def test_update_requires_admin(client):
    assert client.put("/api/v1/branding", data={"app_title": "x"}).status_code == 401
