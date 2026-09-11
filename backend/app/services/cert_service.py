"""Parse and manage CA certificates (spec section 11)."""
from __future__ import annotations

from datetime import datetime, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CaCertificate


class CertificateError(ValueError):
    pass


def parse_certificate(data: str | bytes) -> tuple[dict, str]:
    """Parse a CA certificate (PEM or DER) and return ``(metadata, pem)``.

    Accepts the common Windows export formats - Base64 PEM (.cer/.crt/.pem) and
    binary DER (.cer/.crt/.der). The certificate is always normalised to PEM for
    storage, so the bundle stays usable by ldap3 and FreeRADIUS.
    """
    raw = data.encode() if isinstance(data, str) else data
    cert = None
    try:
        cert = x509.load_pem_x509_certificate(raw)
    except Exception:  # noqa: BLE001 - fall back to DER (binary .cer/.crt)
        try:
            cert = x509.load_der_x509_certificate(raw)
        except Exception as exc:  # noqa: BLE001 - neither format parsed
            raise CertificateError("Not a valid certificate (expected PEM or DER)") from exc

    pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    fp = cert.fingerprint(hashes.SHA256()).hex(":").upper()
    # cryptography >= 42 exposes tz-aware *_utc accessors.
    not_before = getattr(cert, "not_valid_before_utc", None) or cert.not_valid_before.replace(
        tzinfo=timezone.utc
    )
    not_after = getattr(cert, "not_valid_after_utc", None) or cert.not_valid_after.replace(
        tzinfo=timezone.utc
    )
    meta = {
        "subject": cert.subject.rfc4514_string()[:512],
        "issuer": cert.issuer.rfc4514_string()[:512],
        "fingerprint_sha256": fp,
        "not_before": not_before,
        "not_after": not_after,
    }
    return meta, pem


def status_for(not_after: datetime) -> tuple[str, int]:
    """Return ``(status, days_left)`` where status is valid/expiring/expired."""
    now = datetime.now(timezone.utc)
    if not_after.tzinfo is None:
        not_after = not_after.replace(tzinfo=timezone.utc)
    days_left = (not_after - now).days
    if days_left < 0:
        return "expired", days_left
    if days_left <= 30:
        return "expiring", days_left
    return "valid", days_left


def build_bundle(db: Session) -> str | None:
    """Concatenate all stored CA certificates into a single PEM bundle."""
    certs = db.scalars(select(CaCertificate).order_by(CaCertificate.name)).all()
    if not certs:
        return None
    return "\n".join(c.pem.strip() for c in certs) + "\n"
