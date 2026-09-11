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


_GENERATE_HINT = (
    "Generate a valid one with: "
    "python -c \"from cryptography.fernet import Fernet; "
    "print(Fernet.generate_key().decode())\" "
    "(a Fernet key is 32 url-safe base64 bytes, 44 chars ending in '='; "
    "note: token_urlsafe / hex values are NOT valid Fernet keys)."
)


@lru_cache
def _fernet() -> Fernet:
    key = get_settings().fernet_key
    if not key:
        raise SecretCryptoError("FERNET_KEY is not configured. " + _GENERATE_HINT)
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as exc:
        raise SecretCryptoError("FERNET_KEY is not a valid Fernet key. " + _GENERATE_HINT) from exc


def validate_key() -> None:
    """Raise :class:`SecretCryptoError` if FERNET_KEY is missing or invalid.

    Called at startup so misconfiguration is reported immediately and clearly,
    rather than only when the first secret is written.
    """
    _fernet()


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise SecretCryptoError("Stored secret could not be decrypted.") from exc
