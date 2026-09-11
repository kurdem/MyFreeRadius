"""Symmetric encryption of secrets at rest using Fernet (spec sections 6, 26).

Shared secrets and bind passwords are stored encrypted in the database. The key
comes from the ``FERNET_KEY`` environment variable and is never persisted.
"""
from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class SecretCryptoError(RuntimeError):
    pass


@lru_cache
def _fernet() -> Fernet:
    key = get_settings().fernet_key
    if not key:
        raise SecretCryptoError(
            "FERNET_KEY is not configured. Generate one with "
            "`python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\"`."
        )
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as exc:
        raise SecretCryptoError("FERNET_KEY is not a valid Fernet key.") from exc


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise SecretCryptoError("Stored secret could not be decrypted.") from exc
