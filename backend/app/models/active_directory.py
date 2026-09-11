"""Active Directory configuration and allowed groups (spec sections 6, 7).

Phase 3, slice 1: store the AD/LDAP connection settings and the list of allowed
AD groups, and support a real LDAP(S) connection test. Wiring FreeRADIUS to
authenticate users against this AD is the next slice.

The bind password is encrypted at rest (Fernet), like RADIUS shared secrets.
"""
from __future__ import annotations

import enum

from sqlalchemy import Boolean, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ADConfig(Base, TimestampMixin):
    """Singleton AD configuration (a single row, id == 1)."""

    __tablename__ = "ad_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    primary_dc: Mapped[str] = mapped_column(String(255), nullable=False)
    secondary_dc: Mapped[str | None] = mapped_column(String(255), nullable=True)
    port: Mapped[int] = mapped_column(Integer, default=389, nullable=False)
    use_ldaps: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Validate the server certificate for LDAPS. Turning this off is insecure.
    verify_tls: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    base_dn: Mapped[str] = mapped_column(String(512), nullable=False)
    bind_user: Mapped[str] = mapped_column(String(255), nullable=False)
    bind_password_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # --- MFA (Phase 4) ---------------------------------------------------- #
    # When enabled, authentication goes through the backend (rlm_rest) which
    # verifies a TOTP second factor. Modes:
    #   "totp_only"            - RADIUS validates the OTP only; Horizon validates
    #                            the Windows/AD password itself (recommended).
    #   "ad_password_plus_totp"- RADIUS validates AD password + appended 6-digit
    #                            OTP (User-Password = "<ad-password><otp>").
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_mode: Mapped[str] = mapped_column(String(32), default="totp_only", nullable=False)


class GroupAccess(str, enum.Enum):
    ALLOW = "allow"
    DENY = "deny"


class ADGroup(Base, TimestampMixin):
    """An AD group that is allowed (or denied) to authenticate via RADIUS."""

    __tablename__ = "ad_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    group_dn: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    access: Mapped[GroupAccess] = mapped_column(
        Enum(GroupAccess, native_enum=False, length=8),
        default=GroupAccess.ALLOW,
        nullable=False,
    )
    # Optional label to map onto a returned RADIUS attribute later (e.g. Admin).
    attribute: Mapped[str | None] = mapped_column(String(120), nullable=True)
