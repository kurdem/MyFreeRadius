"""Backup and restore of the application configuration (spec section 17).

The backup is a JSON document of the configuration tables. Secrets (shared
secrets, bind password, TOTP secrets) are included **as stored ciphertext**, so
a backup is only usable together with the same ``FERNET_KEY``. Optionally the
whole document can be encrypted with a passphrase.

Not included: the audit log and the generated config-version history (both are
regenerable / append-only).
"""
from __future__ import annotations

import base64
import enum
import hashlib
import json
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from sqlalchemy import DateTime
from sqlalchemy.orm import Session

from app import __version__
from app.config import get_settings
from app.models import (
    ADConfig,
    ADGroup,
    CaCertificate,
    ClientGroup,
    RadiusClient,
    User,
    UserTotp,
)

# Order matters for foreign keys: parents before children on insert, reverse on
# delete (radius_clients references client_groups).
_MODELS = [User, ClientGroup, RadiusClient, ADConfig, ADGroup, UserTotp, CaCertificate]

BACKUP_FORMAT = "freeradius-manager-backup/1"


def _key_fingerprint() -> str:
    return hashlib.sha256(get_settings().fernet_key.encode()).hexdigest()[:16]


def _row_to_json(obj) -> dict:
    out: dict = {}
    for col in obj.__table__.columns:
        v = getattr(obj, col.name)
        if isinstance(v, enum.Enum):
            v = v.value
        elif isinstance(v, datetime):
            v = v.isoformat()
        out[col.name] = v
    return out


def _coerce_row(model, row: dict) -> dict:
    out: dict = {}
    for col in model.__table__.columns:
        v = row.get(col.name)
        if v is not None and isinstance(col.type, DateTime) and isinstance(v, str):
            v = datetime.fromisoformat(v)
        out[col.name] = v
    return out


def export_dict(db: Session) -> dict:
    tables = {m.__tablename__: [_row_to_json(o) for o in db.scalars(_select_all(m))] for m in _MODELS}
    return {
        "format": BACKUP_FORMAT,
        "app_version": __version__,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "fernet_key_fingerprint": _key_fingerprint(),
        "tables": tables,
    }


def _select_all(model):
    from sqlalchemy import select

    return select(model)


# --------------------------------------------------------------------------- #
# Passphrase encryption (optional "encrypted backup")
# --------------------------------------------------------------------------- #
def _derive_key(passphrase: str, salt: bytes) -> bytes:
    kdf = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1)
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))


def serialize(db: Session, passphrase: str | None = None) -> bytes:
    payload = json.dumps(export_dict(db), indent=2).encode()
    if not passphrase:
        return payload
    salt = hashlib.sha256(passphrase.encode() + get_settings().secret_key.encode()).digest()[:16]
    token = Fernet(_derive_key(passphrase, salt)).encrypt(payload)
    envelope = {"format": "freeradius-manager-backup-encrypted/1",
                "salt": base64.b64encode(salt).decode(), "data": token.decode()}
    return json.dumps(envelope).encode()


def deserialize(raw: bytes, passphrase: str | None = None) -> dict:
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise BackupError("File is not a valid backup (not JSON)") from exc

    if isinstance(obj, dict) and obj.get("format") == "freeradius-manager-backup-encrypted/1":
        if not passphrase:
            raise BackupError("This backup is encrypted - a passphrase is required")
        salt = base64.b64decode(obj["salt"])
        try:
            payload = Fernet(_derive_key(passphrase, salt)).decrypt(obj["data"].encode())
        except (InvalidToken, KeyError, ValueError) as exc:
            raise BackupError("Wrong passphrase or corrupted backup") from exc
        obj = json.loads(payload.decode())

    if not isinstance(obj, dict) or obj.get("format") != BACKUP_FORMAT:
        raise BackupError("Unrecognised backup format")
    return obj


class BackupError(ValueError):
    pass


def restore(db: Session, data: dict, *, force: bool = False) -> dict:
    """Replace the configuration tables with the backup content.

    Refuses if the backup was made with a different FERNET_KEY (its secrets
    would be undecryptable) unless ``force`` is set.
    """
    tables = data.get("tables")
    if not isinstance(tables, dict):
        raise BackupError("Backup contains no tables")

    fp = data.get("fernet_key_fingerprint")
    if fp and fp != _key_fingerprint() and not force:
        raise BackupError(
            "This backup was created with a different FERNET_KEY; its encrypted "
            "secrets cannot be decrypted with the current key. Restore with the "
            "matching key, or force the restore to import everything except that "
            "the secrets will be unusable."
        )

    counts: dict[str, int] = {}
    # Delete children first, then insert parents first.
    for model in reversed(_MODELS):
        db.execute(model.__table__.delete())
    for model in _MODELS:
        rows = tables.get(model.__tablename__, [])
        if rows:
            db.execute(model.__table__.insert(), [_coerce_row(model, r) for r in rows])
        counts[model.__tablename__] = len(rows)
    db.commit()
    return counts
