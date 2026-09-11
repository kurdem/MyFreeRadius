"""TOTP helpers (Phase 4). Secrets are stored encrypted at rest."""
from __future__ import annotations

import pyotp

from app.security.crypto import decrypt_secret, encrypt_secret

# Allow one step of clock drift on either side.
_VALID_WINDOW = 1


def new_secret() -> str:
    return pyotp.random_base32()


def encrypt(secret: str) -> str:
    return encrypt_secret(secret)


def provisioning_uri(secret: str, username: str, issuer: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=issuer)


def verify(secret_encrypted: str, code: str) -> bool:
    if not code or not code.isdigit():
        return False
    secret = decrypt_secret(secret_encrypted)
    return pyotp.TOTP(secret).verify(code, valid_window=_VALID_WINDOW)
