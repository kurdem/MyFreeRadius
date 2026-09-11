"""Parse and manage CA certificates (spec section 11)."""
from __future__ import annotations

from datetime import datetime, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CaCertificate


class CertificateError(ValueError):
    pass


def parse_certificate(pem: str) -> dict:
    """Parse a PEM CA certificate and return its metadata.

    Only the first certificate in the PEM is used for metadata; the whole PEM is
    stored so a chain can be provided.
    """
    try:
        cert = x509.load_pem_x509_certificate(pem.encode())
    except Exception as exc:  # noqa: BLE001 - any parse error is a bad upload
        raise CertificateError("Not a valid PEM certificate") from exc

    fp = cert.fingerprint(hashes.SHA256()).hex(":").upper()
    # cryptography >= 42 exposes tz-aware *_utc accessors.
    not_before = getattr(cert, "not_valid_before_utc", None) or cert.not_valid_before.replace(
        tzinfo=timezone.utc
    )
    not_after = getattr(cert, "not_valid_after_utc", None) or cert.not_valid_after.replace(
        tzinfo=timezone.utc
    )
    return {
        "subject": cert.subject.rfc4514_string()[:512],
        "issuer": cert.issuer.rfc4514_string()[:512],
        "fingerprint_sha256": fp,
        "not_before": not_before,
        "not_after": not_after,
    }


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
