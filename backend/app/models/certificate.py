"""CA certificates for LDAPS validation (spec section 11).

Only CA certificates (public, non-secret) are stored here - used to validate the
TLS connection to Active Directory over LDAPS. No private keys are handled.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class CaCertificate(Base, TimestampMixin):
    __tablename__ = "ca_certificates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    pem: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(String(512), nullable=False)
    issuer: Mapped[str] = mapped_column(String(512), nullable=False)
    fingerprint_sha256: Mapped[str] = mapped_column(String(95), unique=True, nullable=False)
    not_before: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    not_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
