"""Branding: custom logo and application title (issue #20)."""
from __future__ import annotations

from sqlalchemy import Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class BrandingConfig(Base, TimestampMixin):
    __tablename__ = "branding"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    app_title: Mapped[str] = mapped_column(String(120), default="FreeRADIUS Manager", nullable=False)
    # Issuer shown in the authenticator app for TOTP enrollments (company name / label).
    otp_issuer: Mapped[str] = mapped_column(String(120), default="FreeRADIUS Manager", nullable=False)
    logo: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    logo_content_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
