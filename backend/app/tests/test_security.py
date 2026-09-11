"""Security-focused tests: crypto at rest, RBAC, log masking (spec sections 6, 22, 26)."""
from __future__ import annotations

from app.logging_conf import _mask
from app.security.crypto import decrypt_secret, encrypt_secret
from app.security.passwords import hash_password, verify_password


def test_secret_roundtrip_and_not_plaintext():
    token = encrypt_secret("MyShared!Secret")
    assert token != "MyShared!Secret"
    assert decrypt_secret(token) == "MyShared!Secret"


def test_invalid_fernet_key_raises_actionable_error(monkeypatch):
    import app.security.crypto as crypto
    from app.config import get_settings

    crypto._fernet.cache_clear()
    settings = get_settings()
    monkeypatch.setattr(settings, "fernet_key", "not-a-valid-fernet-key", raising=False)
    try:
        with __import__("pytest").raises(crypto.SecretCryptoError) as exc:
            crypto.validate_key()
        assert "Fernet" in str(exc.value)
        assert "generate_key" in str(exc.value)  # actionable hint present
    finally:
        crypto._fernet.cache_clear()  # restore valid key for other tests


def test_password_hash_is_argon2id():
    h = hash_password("correct horse battery staple")
    assert h.startswith("$argon2id$")
    assert verify_password("correct horse battery staple", h)
    assert not verify_password("wrong", h)


def test_log_masking_redacts_secrets():
    assert "REDACTED" in _mask('secret="hunter2"')
    assert "REDACTED" in _mask("password: superpass")
    assert "hunter2" not in _mask('shared_secret=hunter2')


def test_security_headers_present(client):
    resp = client.get("/api/v1/health")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"


def test_health_is_public(client):
    assert client.get("/api/v1/health").status_code == 200
