"""One-time self-service MFA enrollment links (issue #11).

An administrator creates a link for a user; the user opens it (no login), scans
the QR code and confirms a code. The link is single-use and time-limited. The
pending TOTP secret is stored (encrypted) on the token so page reloads keep the
same QR until the user confirms.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class MfaEnrollmentToken(Base, TimestampMixin):
    __tablename__ = "mfa_enrollment_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(128), nullable=False)
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
